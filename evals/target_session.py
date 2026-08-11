#!/usr/bin/env python3
"""Resumable, hash-bound target execution with independent human review.

The stdio adapter receives no expected events, branches, forbidden labels, or
rubric scores. A run pauses after every model completion until a schema-valid
two-reviewer packet is imported. Completed sessions are replayed through the
same automated safety/hard-gate runtime used by synthetic conformance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

import run as harness

ROOT = Path(__file__).resolve().parents[1]
TARGET_CONFIG_SCHEMA = ROOT / "evals/target-config.schema.json"
HUMAN_REVIEW_SCHEMA = ROOT / "evals/human-review.schema.json"
TARGET_RESULT_SCHEMA = ROOT / "evals/results/TARGET_RUN_SCHEMA.json"
RUBRIC_DIMENSIONS = (
    "collaborative_inquiry",
    "context_model_integrity",
    "action_fit",
    "agency_and_challenge",
    "continuity_and_privacy",
    "language_and_specificity",
    "safety_and_scope",
)
BASELINES = {
    "direct_assistant": ROOT / "evals/baselines/direct_assistant.yaml",
    "structured_reflection": ROOT / "evals/baselines/structured_reflection.yaml",
}
RESERVED_ENVIRONMENT_NAMES = {"PATH", "LANG", "LC_ALL", "ENV", "BASH_ENV", "IFS"}
RESERVED_ENVIRONMENT_PREFIXES = (
    "PYTHON",
    "LD_",
    "DYLD_",
    "NODE_",
    "RUBY",
    "PERL",
    "JAVA_TOOL_OPTIONS",
)
SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "authorization",
    "cookie",
    "bearer",
    "client_secret",
    "access_key",
    "signing_key",
)
SENSITIVE_EXACT_KEYS = {"auth", "headers", "session"}
PROVIDER_RESPONSE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


class TargetEvaluationError(RuntimeError):
    pass


class ProviderProtocolError(TargetEvaluationError):
    pass


class ReviewImportError(TargetEvaluationError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TargetEvaluationError("clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise TargetEvaluationError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TargetEvaluationError(f"{field} must be timezone aware")
    return parsed.astimezone(timezone.utc)


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in SENSITIVE_EXACT_KEYS
            or any(fragment in str(key).lower() for fragment in SENSITIVE_KEY_FRAGMENTS)
            or _contains_sensitive_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def expected_run_plan(
    suite: dict[str, Any], case_ids: list[str], systems: list[str]
) -> list[dict[str, Any]]:
    selected = set(case_ids)
    return [
        {
            "case_id": case["id"],
            "system_id": system_id,
            "variant_id": variant["id"],
            "repetition": repetition,
        }
        for case in suite["cases"]
        if case["id"] in selected
        for system_id in systems
        for variant in case["entry_variants"]
        for repetition in range(1, case["repetitions"] + 1)
    ]


def _schema_errors(value: object, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in errors
    ]


def validate_target_config(config: dict[str, Any], suite: dict[str, Any]) -> list[str]:
    errors = _schema_errors(config, TARGET_CONFIG_SCHEMA)
    if errors:
        return errors
    if config["suite_sha256"] != _digest(suite):
        errors.append("suite_sha256 does not match the supplied suite")
    if set(config["systems"]) != set(suite["required_systems"]):
        errors.append("systems do not exactly match the suite")
    known_cases = {case["id"] for case in suite["cases"]}
    if unknown := set(config["case_ids"]) - known_cases:
        errors.append(f"unknown case ids: {sorted(unknown)}")
    expected_baselines = {
        name: _file_sha256(path) for name, path in BASELINES.items()
    }
    if config["baseline_sha256"] != expected_baselines:
        errors.append("baseline_sha256 does not match both governed baselines")
    if not unknown:
        expected_plan = expected_run_plan(
            suite, config["case_ids"], config["systems"]
        )
        if config["run_plan"] != expected_plan:
            errors.append("run_plan is not the complete deterministic selected-case matrix")
    expected_skill_hash = _file_sha256(ROOT / "skill/personal-growth-copilot/SKILL.md")
    if config["provider"]["skill_sha256"] != expected_skill_hash:
        errors.append("skill_sha256 does not match the current skill")
    expected_rubric_hash = _file_sha256(ROOT / "evals/rubric.md")
    if config["review"]["rubric_sha256"] != expected_rubric_hash:
        errors.append("rubric_sha256 does not match the current rubric")
    if _contains_sensitive_key(config["provider"]["settings"]):
        errors.append("provider settings contain a secret-like key")
    environment_names = set(config["provider"]["environment_allowlist"])
    for name in sorted(environment_names):
        if name in RESERVED_ENVIRONMENT_NAMES or name.startswith(
            RESERVED_ENVIRONMENT_PREFIXES
        ):
            errors.append(f"provider environment name is reserved: {name}")
    roster = config["review"]["reviewer_roster"]
    reviewer_ids = [entry["reviewer_id"] for entry in roster]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        errors.append("reviewer roster ids must be unique")
    if any(
        case["language"] in {"zh", "mixed"}
        for case in suite["cases"]
        if case["id"] in set(config["case_ids"])
    ):
        fluent_count = sum(
            bool({"zh", "mixed"} & set(entry["languages"])) for entry in roster
        )
        if fluent_count < 3:
            errors.append("Chinese/mixed target plans require three fluent rostered reviewers")
    return errors


def provider_identity(config: dict[str, Any]) -> str:
    return _digest(
        {
            "source_commit": config["source_commit"],
            "provider": config["provider"],
            "frozen_at": config["frozen_at"],
        }
    )


@dataclass(frozen=True)
class CapturedCompletion:
    request_sha256: str
    provider_identity_sha256: str
    text: str
    memory_write_attempted: bool
    resource_claims: tuple[dict[str, str], ...]
    provider_response_id: str
    captured_at: str
    completion_sha256: str


class FrozenStdioProvider:
    """Call one explicitly frozen executable with JSON stdin and no shell."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        adapter_path: Path,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = 120,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = deepcopy(config)
        self._execution_lock = RLock()
        if adapter_path.is_symlink():
            raise ProviderProtocolError("adapter path may not be a symlink")
        resolved_adapter = adapter_path.resolve()
        self._clock = clock
        if not resolved_adapter.is_file():
            raise ProviderProtocolError("adapter path is not a file")
        if not os.access(resolved_adapter, os.X_OK):
            raise ProviderProtocolError("adapter is not executable")
        adapter_bytes = resolved_adapter.read_bytes()
        if hashlib.sha256(adapter_bytes).hexdigest() != config["provider"]["adapter_sha256"]:
            raise ProviderProtocolError("adapter sha256 mismatch")
        self._expected_adapter_sha256 = config["provider"]["adapter_sha256"]
        self._snapshot_directory = tempfile.TemporaryDirectory(prefix="pgc-frozen-adapter-")
        self._adapter_path = Path(self._snapshot_directory.name) / "adapter"
        descriptor = os.open(
            self._adapter_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o500,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(adapter_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            self._snapshot_directory.cleanup()
            raise
        os.chmod(self._adapter_path, 0o500)
        if not 1 <= timeout_seconds <= 600:
            raise ProviderProtocolError("timeout must be from 1 through 600 seconds")
        self._timeout = timeout_seconds
        supplied = dict(environment or {})
        allowed = set(config["provider"]["environment_allowlist"])
        if set(supplied) - allowed:
            raise ProviderProtocolError("environment contains a non-allowlisted key")
        self._environment = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "LANG": "C.UTF-8",
            **supplied,
        }
        self.identity_sha256 = provider_identity(config)
        self._used_response_ids: set[str] = set()
        self._response_lock = Lock()

    def close(self) -> None:
        lock = getattr(self, "_execution_lock", None)
        if lock is None:
            return
        with lock:
            directory = getattr(self, "_snapshot_directory", None)
            if directory is not None:
                directory.cleanup()
                self._snapshot_directory = None

    def __enter__(self) -> "FrozenStdioProvider":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @staticmethod
    def request_payload(
        request: harness.CompletionRequest, identity_sha256: str
    ) -> dict[str, Any]:
        return {
            "protocol": "pgc-stdio-v1",
            "provider_identity_sha256": identity_sha256,
            "request": {
                "system_id": request.system_id,
                "case_id": request.case_id,
                "variant_id": request.variant_id,
                "repetition": request.repetition,
                "turn_id": request.turn_id,
                "user": request.user,
                "history": [list(item) for item in request.history],
            },
        }

    def complete(self, request: harness.CompletionRequest) -> CapturedCompletion:
        with self._execution_lock:
            return self._complete(request)

    def _complete(self, request: harness.CompletionRequest) -> CapturedCompletion:
        if self._snapshot_directory is None or not self._adapter_path.is_file():
            raise ProviderProtocolError("frozen adapter snapshot is unavailable")
        if _file_sha256(self._adapter_path) != self._expected_adapter_sha256:
            raise ProviderProtocolError("frozen adapter snapshot changed before invocation")
        payload = self.request_payload(request, self.identity_sha256)
        request_sha256 = _digest(payload)
        try:
            result = subprocess.run(
                [str(self._adapter_path)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                env=self._environment,
                cwd=self._snapshot_directory.name,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderProtocolError(f"adapter execution failed: {type(exc).__name__}") from exc
        if result.returncode != 0:
            raise ProviderProtocolError(f"adapter exited {result.returncode}")
        if len(result.stdout.encode("utf-8")) > 1_048_576:
            raise ProviderProtocolError("adapter stdout exceeds one MiB")
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError("adapter stdout is not one JSON value") from exc
        allowed_keys = {
            "protocol",
            "request_sha256",
            "provider_identity_sha256",
            "text",
            "memory_write_attempted",
            "resource_claims",
            "provider_response_id",
        }
        if not isinstance(response, dict) or set(response) != allowed_keys:
            raise ProviderProtocolError("adapter response fields do not match the protocol")
        if response["protocol"] != "pgc-stdio-v1":
            raise ProviderProtocolError("adapter protocol mismatch")
        if response["request_sha256"] != request_sha256:
            raise ProviderProtocolError("adapter did not bind the request")
        if response["provider_identity_sha256"] != self.identity_sha256:
            raise ProviderProtocolError("adapter provider identity mismatch")
        if not isinstance(response["text"], str) or not response["text"].strip():
            raise ProviderProtocolError("adapter text must be non-empty")
        if not isinstance(response["memory_write_attempted"], bool):
            raise ProviderProtocolError("memory_write_attempted must be boolean")
        if not isinstance(response["provider_response_id"], str) or not PROVIDER_RESPONSE_ID.fullmatch(
            response["provider_response_id"]
        ):
            raise ProviderProtocolError("provider_response_id must be opaque and protocol-safe")
        with self._response_lock:
            if response["provider_response_id"] in self._used_response_ids:
                raise ProviderProtocolError("provider_response_id must be unique")
            self._used_response_ids.add(response["provider_response_id"])
        claims: list[dict[str, str]] = []
        if not isinstance(response["resource_claims"], list):
            raise ProviderProtocolError("resource_claims must be an array")
        for claim in response["resource_claims"]:
            if (
                not isinstance(claim, dict)
                or set(claim) != {"name", "contact", "source_uri"}
                or not all(isinstance(value, str) and value for value in claim.values())
            ):
                raise ProviderProtocolError("malformed resource claim")
            claims.append(dict(claim))
        captured = {
            "request_sha256": request_sha256,
            "provider_identity_sha256": self.identity_sha256,
            "text": response["text"],
            "memory_write_attempted": response["memory_write_attempted"],
            "resource_claims": claims,
            "provider_response_id": response["provider_response_id"],
            "captured_at": _timestamp(self._clock()),
        }
        return CapturedCompletion(
            **captured,
            completion_sha256=_digest(captured),
        )


def blinded_run_id(completion_sha256: str) -> str:
    return "blind_" + _digest(
        {"domain": "pgc-human-review-v1", "completion_sha256": completion_sha256}
    )[:32]


def validate_review_packet(
    packet: dict[str, Any],
    *,
    completion_sha256: str,
    captured_at: str,
    imported_at: datetime,
    language: str,
    config: dict[str, Any],
) -> list[str]:
    errors = _schema_errors(packet, HUMAN_REVIEW_SCHEMA)
    if errors:
        return errors
    if packet["completion_sha256"] != completion_sha256:
        errors.append("completion_sha256 mismatch")
    if packet["blinded_run_id"] != blinded_run_id(completion_sha256):
        errors.append("blinded_run_id mismatch")
    if packet["identity_verification"] != config["review"]["identity_verification"]:
        errors.append("review identity-verification state mismatch")
    reviewers = packet["reviewers"]
    reviewer_ids = [reviewer["reviewer_id"] for reviewer in reviewers]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        errors.append("reviewer ids must be unique")
    reviewer_roles = [reviewer["role"] for reviewer in reviewers]
    if len(reviewer_roles) != len(set(reviewer_roles)):
        errors.append("reviewer roles must be unique")
    roster = {
        entry["reviewer_id"]: entry for entry in config["review"]["reviewer_roster"]
    }
    if unknown_reviewers := sorted(set(reviewer_ids) - set(roster)):
        errors.append(f"reviewer ids are absent from the frozen roster: {unknown_reviewers}")
    if language.lower().startswith("zh") and config["review"][
        "chinese_fluency_required"
    ]:
        if any(not reviewer["language_fluent"] for reviewer in reviewers):
            errors.append("every Chinese-case reviewer must attest fluency")
        if any(
            reviewer_id in roster
            and not ({"zh", "mixed"} & set(roster[reviewer_id]["languages"]))
            for reviewer_id in reviewer_ids
        ):
            errors.append("every Chinese-case reviewer must be fluent in the frozen roster")
    try:
        captured = _parse_timestamp(captured_at, field="captured_at")
        if imported_at.tzinfo is None or imported_at.utcoffset() is None:
            raise TargetEvaluationError("review import clock must be timezone aware")
        imported = imported_at.astimezone(timezone.utc)
        submitted = [
            _parse_timestamp(reviewer["submitted_at"], field="reviewer submitted_at")
            for reviewer in reviewers
        ]
        decided = _parse_timestamp(
            packet["adjudication"]["decided_at"], field="adjudication decided_at"
        )
    except (TargetEvaluationError, AttributeError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    else:
        if any(value < captured for value in submitted):
            errors.append("review submission precedes the captured completion")
        if any(value > imported for value in submitted) or decided > imported:
            errors.append("review chronology extends beyond the import time")
        if submitted and decided < max(submitted):
            errors.append("adjudication precedes a reviewer submission")
    adjudication = packet["adjudication"]
    comparable_fields = (
        "events",
        "scores",
        "hard_failure_codes",
        "resource_claims_reviewed",
    )
    if adjudication["method"] == "consensus":
        if len(reviewers) != 2:
            errors.append("consensus packets require exactly two reviewers")
        if set(reviewer_roles) != {"primary_1", "primary_2"}:
            errors.append("consensus packets require the two primary reviewer roles")
        if reviewers and any(
            reviewer[field] != reviewers[0][field]
            for reviewer in reviewers[1:]
            for field in comparable_fields
        ):
            errors.append("consensus method cannot conceal reviewer disagreement")
        if reviewers and any(
            adjudication[field] != reviewers[0][field] for field in comparable_fields
        ):
            errors.append("consensus adjudication differs from reviewer labels")
        if adjudication["disagreements"]:
            errors.append("consensus packet may not declare disagreements")
        if adjudication["adjudicator_id"] not in reviewer_ids:
            errors.append("consensus adjudicator must be one of the reviewers")
    else:
        if len(reviewers) != 3:
            errors.append("third-reviewer adjudication requires three reviewers")
        if set(reviewer_roles) != {"primary_1", "primary_2", "third_reviewer"}:
            errors.append("third-reviewer packets require all three reviewer roles")
        third_reviewer_ids = [
            reviewer["reviewer_id"]
            for reviewer in reviewers
            if reviewer["role"] == "third_reviewer"
        ]
        if adjudication["adjudicator_id"] not in third_reviewer_ids:
            errors.append("the rostered third reviewer must be the adjudicator")
        if not adjudication["disagreements"]:
            errors.append("third-reviewer adjudication must state the disagreements")
        match = next(
            (
                reviewer
                for reviewer in reviewers
                if reviewer["reviewer_id"] == adjudication["adjudicator_id"]
            ),
            None,
        )
        if match and any(adjudication[field] != match[field] for field in comparable_fields):
            errors.append("adjudication differs from the identified third reviewer")
    return errors


class TargetSession:
    def __init__(
        self,
        *,
        suite: dict[str, Any],
        config: dict[str, Any],
        case_id: str,
        system_id: str,
        variant_id: str,
        repetition: int,
        clock: Callable[[], datetime],
    ) -> None:
        suite_snapshot = deepcopy(suite)
        config_snapshot = deepcopy(config)
        if suite_errors := harness.validate_suite(suite_snapshot):
            raise TargetEvaluationError("invalid suite: " + "; ".join(suite_errors))
        if config_errors := validate_target_config(config_snapshot, suite_snapshot):
            raise TargetEvaluationError("invalid target config: " + "; ".join(config_errors))
        if system_id not in config_snapshot["systems"]:
            raise TargetEvaluationError("system is not in the frozen config")
        if repetition < 1:
            raise TargetEvaluationError("repetition must be positive")
        try:
            case = next(item for item in suite_snapshot["cases"] if item["id"] == case_id)
            variant = next(
                item for item in case["entry_variants"] if item["id"] == variant_id
            )
        except StopIteration as exc:
            raise TargetEvaluationError("unknown case or variant") from exc
        run_identity = {
            "case_id": case_id,
            "system_id": system_id,
            "variant_id": variant_id,
            "repetition": repetition,
        }
        if run_identity not in config_snapshot["run_plan"]:
            raise TargetEvaluationError("run identity is outside the preregistered run plan")
        self._suite = suite_snapshot
        self._config = config_snapshot
        self._case = case
        self._variant = variant
        self._clock = clock
        self._lock = RLock()
        self.system_id = system_id
        self.repetition = repetition
        self.current_turn_id: str | None = case["entry_turn"]
        self.status = "AWAITING_PROVIDER"
        self.transcript: list[dict[str, Any]] = []
        self.pending_completion: CapturedCompletion | None = None
        self.branch_error: str | None = None

    def pending_request(self) -> harness.CompletionRequest:
        if self.status != "AWAITING_PROVIDER" or self.current_turn_id is None:
            raise TargetEvaluationError("session is not awaiting a provider")
        turn = next(item for item in self._case["turns"] if item["id"] == self.current_turn_id)
        user = (
            self._variant["text"]
            if self.current_turn_id == self._case["entry_turn"]
            else turn["user"]
        )
        history: list[tuple[str, str]] = []
        for captured in self.transcript:
            history.extend(
                (
                    ("user", captured["request"]["user"]),
                    ("assistant", captured["completion"]["text"]),
                )
            )
        return harness.CompletionRequest(
            system_id=self.system_id,
            case_id=self._case["id"],
            variant_id=self._variant["id"],
            repetition=self.repetition,
            turn_id=self.current_turn_id,
            user=user,
            history=tuple(history),
        )

    def capture(self, provider: FrozenStdioProvider) -> CapturedCompletion:
        with self._lock:
            return self._capture(provider)

    def _capture(self, provider: FrozenStdioProvider) -> CapturedCompletion:
        if provider.identity_sha256 != provider_identity(self._config):
            raise TargetEvaluationError("provider identity differs from the session freeze")
        request = self.pending_request()
        returned = provider.complete(request)
        if not isinstance(returned, CapturedCompletion):
            raise TargetEvaluationError("provider returned a malformed captured completion")
        completion = _validated_captured_completion(
            asdict(returned), request=request, config=self._config
        )
        if completion.provider_response_id in {
            captured["completion"]["provider_response_id"] for captured in self.transcript
        }:
            raise TargetEvaluationError("provider_response_id was already used in this session")
        self.pending_completion = completion
        self.status = "AWAITING_HUMAN_REVIEW"
        return completion

    def import_review(self, packet: dict[str, Any]) -> None:
        with self._lock:
            self._import_review(packet)

    def _import_review(self, packet: dict[str, Any]) -> None:
        if self.status != "AWAITING_HUMAN_REVIEW" or self.pending_completion is None:
            raise ReviewImportError("session has no completion awaiting review")
        request = self.pending_request_for_review()
        imported_at = self._clock()
        if errors := validate_review_packet(
            packet,
            completion_sha256=self.pending_completion.completion_sha256,
            captured_at=self.pending_completion.captured_at,
            imported_at=imported_at,
            language=self._case["language"],
            config=self._config,
        ):
            raise ReviewImportError("; ".join(errors))
        turn = next(item for item in self._case["turns"] if item["id"] == request.turn_id)
        events = set(packet["adjudication"]["events"])
        next_turn: str | None = None
        selected_branch: str | None = None
        if not turn["terminal"]:
            matches = [
                branch
                for branch in turn["branches"]
                if set(branch["when_all"]).issubset(events)
                and not set(branch.get("when_none", [])) & events
            ]
            if len(matches) == 1:
                selected_branch = matches[0]["id"]
                next_turn = matches[0]["next_turn"]
            else:
                self.branch_error = (
                    "AMBIGUOUS_BRANCH" if len(matches) > 1 else "BRANCH_UNRESOLVED"
                )
        completion = asdict(self.pending_completion)
        self.transcript.append(
            {
                "sequence": len(self.transcript) + 1,
                "request": {
                    **asdict(request),
                    "history": [list(item) for item in request.history],
                },
                "completion": {**completion, "resource_claims": list(completion["resource_claims"])},
                "review": deepcopy(packet),
                "review_sha256": _digest(packet),
                "selected_branch": selected_branch,
            }
        )
        self.pending_completion = None
        if turn["terminal"] or next_turn is None:
            self.current_turn_id = None
            self.status = "COMPLETE"
        else:
            self.current_turn_id = next_turn
            self.status = "AWAITING_PROVIDER"

    def pending_request_for_review(self) -> harness.CompletionRequest:
        if self.current_turn_id is None:
            raise ReviewImportError("session has no current turn")
        turn = next(item for item in self._case["turns"] if item["id"] == self.current_turn_id)
        user = (
            self._variant["text"]
            if self.current_turn_id == self._case["entry_turn"]
            else turn["user"]
        )
        history: list[tuple[str, str]] = []
        for captured in self.transcript:
            history.extend(
                (
                    ("user", captured["request"]["user"]),
                    ("assistant", captured["completion"]["text"]),
                )
            )
        return harness.CompletionRequest(
            self.system_id,
            self._case["id"],
            self._variant["id"],
            self.repetition,
            self.current_turn_id,
            user,
            tuple(history),
        )

    def to_artifact(self) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0",
            "evidence_class": "authored-target-session",
            "qualification_claim_allowed": False,
            "status": self.status,
            "source_commit": self._config["source_commit"],
            "suite_id": self._suite["suite_id"],
            "suite_sha256": _digest(self._suite),
            "config_sha256": _digest(self._config),
            "provider_identity_sha256": provider_identity(self._config),
            "case_sha256": _digest(self._case),
            "variant_sha256": _digest(self._variant),
            "run_identity": {
                "case_id": self._case["id"],
                "system_id": self.system_id,
                "variant_id": self._variant["id"],
                "repetition": self.repetition,
            },
            "current_turn_id": self.current_turn_id,
            "branch_error": self.branch_error,
            "pending_completion": (
                {
                    **asdict(self.pending_completion),
                    "resource_claims": list(self.pending_completion.resource_claims),
                }
                if self.pending_completion
                else None
            ),
            "transcript": deepcopy(self.transcript),
            "updated_at": _timestamp(self._clock()),
        }
        payload["aggregate_sha256"] = _digest(payload)
        return payload

    @classmethod
    def from_artifact(
        cls,
        *,
        suite: dict[str, Any],
        config: dict[str, Any],
        artifact: dict[str, Any],
        clock: Callable[[], datetime],
    ) -> "TargetSession":
        candidate = deepcopy(artifact)
        expected_aggregate = candidate.pop("aggregate_sha256", None)
        if expected_aggregate != _digest(candidate):
            raise TargetEvaluationError("session aggregate_sha256 mismatch")
        required_keys = {
            "schema_version",
            "evidence_class",
            "qualification_claim_allowed",
            "status",
            "source_commit",
            "suite_id",
            "suite_sha256",
            "config_sha256",
            "provider_identity_sha256",
            "case_sha256",
            "variant_sha256",
            "run_identity",
            "current_turn_id",
            "branch_error",
            "pending_completion",
            "transcript",
            "updated_at",
            "aggregate_sha256",
        }
        if set(artifact) != required_keys:
            raise TargetEvaluationError("session artifact fields do not match the contract")
        if artifact["schema_version"] != "1.0" or artifact[
            "evidence_class"
        ] != "authored-target-session" or artifact["qualification_claim_allowed"] is not False:
            raise TargetEvaluationError("session artifact claim class mismatch")
        if artifact["suite_sha256"] != _digest(suite) or artifact["config_sha256"] != _digest(
            config
        ):
            raise TargetEvaluationError("session suite/config identity mismatch")
        identity = artifact["run_identity"]
        restored = cls(
            suite=suite,
            config=config,
            case_id=identity["case_id"],
            system_id=identity["system_id"],
            variant_id=identity["variant_id"],
            repetition=identity["repetition"],
            clock=clock,
        )
        if (
            artifact["source_commit"] != config["source_commit"]
            or artifact["provider_identity_sha256"] != provider_identity(config)
            or artifact["case_sha256"] != _digest(restored._case)
            or artifact["variant_sha256"] != _digest(restored._variant)
        ):
            raise TargetEvaluationError("session frozen identity mismatch")
        original_transcript = deepcopy(artifact["transcript"])
        for captured in original_transcript:
            request = restored.pending_request()
            expected_request = {
                **asdict(request),
                "history": [list(item) for item in request.history],
            }
            if captured.get("request") != expected_request:
                raise TargetEvaluationError("session request chain mismatch")
            completion = _validated_captured_completion(
                captured.get("completion"), request=request, config=config
            )
            restored.pending_completion = completion
            restored.status = "AWAITING_HUMAN_REVIEW"
            restored.import_review(captured.get("review"))
            if restored.transcript[-1] != captured:
                raise TargetEvaluationError("session review/branch chain mismatch")
        pending = artifact["pending_completion"]
        if pending is not None:
            if restored.status != "AWAITING_PROVIDER":
                raise TargetEvaluationError("pending completion conflicts with restored state")
            request = restored.pending_request()
            restored.pending_completion = _validated_captured_completion(
                pending, request=request, config=config
            )
            restored.status = "AWAITING_HUMAN_REVIEW"
        if (
            restored.status != artifact["status"]
            or restored.current_turn_id != artifact["current_turn_id"]
            or restored.branch_error != artifact["branch_error"]
        ):
            raise TargetEvaluationError("restored session state mismatch")
        return restored


def _validated_captured_completion(
    value: Any,
    *,
    request: harness.CompletionRequest,
    config: dict[str, Any],
) -> CapturedCompletion:
    if not isinstance(value, dict):
        raise TargetEvaluationError("captured completion is not an object")
    expected_keys = {
        "request_sha256",
        "provider_identity_sha256",
        "text",
        "memory_write_attempted",
        "resource_claims",
        "provider_response_id",
        "captured_at",
        "completion_sha256",
    }
    if set(value) != expected_keys:
        raise TargetEvaluationError("captured completion fields mismatch")
    identity = provider_identity(config)
    request_payload = FrozenStdioProvider.request_payload(request, identity)
    if value["request_sha256"] != _digest(request_payload):
        raise TargetEvaluationError("captured request hash mismatch")
    if value["provider_identity_sha256"] != identity:
        raise TargetEvaluationError("captured provider identity mismatch")
    if not isinstance(value["text"], str) or not value["text"].strip():
        raise TargetEvaluationError("captured text is invalid")
    if not isinstance(value["memory_write_attempted"], bool):
        raise TargetEvaluationError("captured memory flag is invalid")
    if not isinstance(value["provider_response_id"], str) or not PROVIDER_RESPONSE_ID.fullmatch(
        value["provider_response_id"]
    ):
        raise TargetEvaluationError("captured response id is invalid")
    captured_at = _parse_timestamp(value["captured_at"], field="captured_at")
    if captured_at < _parse_timestamp(config["frozen_at"], field="frozen_at"):
        raise TargetEvaluationError("captured_at precedes the frozen configuration")
    claims = value["resource_claims"]
    if not isinstance(claims, (list, tuple)):
        raise TargetEvaluationError("captured resource claims are invalid")
    normalized_claims: list[dict[str, str]] = []
    for claim in claims:
        if (
            not isinstance(claim, dict)
            or set(claim) != {"name", "contact", "source_uri"}
            or not all(isinstance(item, str) and item for item in claim.values())
        ):
            raise TargetEvaluationError("captured resource claim is malformed")
        normalized_claims.append(dict(claim))
    base = {key: deepcopy(value[key]) for key in expected_keys - {"completion_sha256"}}
    base["resource_claims"] = normalized_claims
    if value["completion_sha256"] != _digest(base):
        raise TargetEvaluationError("completion_sha256 mismatch")
    return CapturedCompletion(
        request_sha256=value["request_sha256"],
        provider_identity_sha256=value["provider_identity_sha256"],
        text=value["text"],
        memory_write_attempted=value["memory_write_attempted"],
        resource_claims=tuple(normalized_claims),
        provider_response_id=value["provider_response_id"],
        captured_at=value["captured_at"],
        completion_sha256=value["completion_sha256"],
    )


class _ReplayProvider:
    def __init__(self, transcript: list[dict[str, Any]]):
        self._transcript = transcript
        self._index = 0

    def complete(self, request: harness.CompletionRequest) -> harness.ModelTurn:
        if self._index >= len(self._transcript):
            raise TargetEvaluationError("replay requested an uncaptured completion")
        captured = self._transcript[self._index]
        expected = deepcopy(captured["request"])
        expected["history"] = [tuple(item) for item in expected["history"]]
        observed = asdict(request)
        observed["history"] = list(observed["history"])
        if observed != expected:
            raise TargetEvaluationError("captured request does not match deterministic replay")
        self._index += 1
        completion = captured["completion"]
        return harness.ModelTurn(
            text=completion["text"],
            memory_write_attempted=completion["memory_write_attempted"],
            resource_claims=tuple(deepcopy(completion["resource_claims"])),
        )


class _ImportedGrader:
    def __init__(self, transcript: list[dict[str, Any]]):
        self._transcript = transcript
        self._index = 0

    def grade(self, request, output, case, turn) -> harness.TurnGrade:
        if self._index >= len(self._transcript):
            raise TargetEvaluationError("replay requested an unreviewed turn")
        review = self._transcript[self._index]["review"]
        self._index += 1
        adjudication = review["adjudication"]
        return harness.TurnGrade(
            events=tuple(adjudication["events"]),
            grader_id=adjudication["adjudicator_id"],
            grader_version=_file_sha256(ROOT / "evals/rubric.md")[:16],
            method="human",
            resource_claims_reviewed=adjudication["resource_claims_reviewed"],
        )


def _quadratic_weighted_kappa(left: list[int], right: list[int]) -> float:
    if len(left) != len(right) or not left:
        raise TargetEvaluationError("weighted kappa requires paired non-empty ratings")
    ratings = range(1, 6)
    observed = {(i, j): 0 for i in ratings for j in ratings}
    left_counts = {i: 0 for i in ratings}
    right_counts = {i: 0 for i in ratings}
    for first, second in zip(left, right, strict=True):
        observed[(first, second)] += 1
        left_counts[first] += 1
        right_counts[second] += 1
    count = len(left)
    weighted_observed = sum(
        (((i - j) / 4) ** 2) * observed[(i, j)] / count
        for i in ratings
        for j in ratings
    )
    weighted_expected = sum(
        (((i - j) / 4) ** 2)
        * (left_counts[i] / count)
        * (right_counts[j] / count)
        for i in ratings
        for j in ratings
    )
    if weighted_expected == 0:
        return 1.0 if weighted_observed == 0 else 0.0
    return max(-1.0, min(1.0, 1.0 - weighted_observed / weighted_expected))


def _quality_summary(
    transcript: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    adjudicated: dict[str, list[int]] = {name: [] for name in RUBRIC_DIMENSIONS}
    left: list[int] = []
    right: list[int] = []
    for captured in transcript:
        packet = captured["review"]
        primary = {
            reviewer["role"]: reviewer
            for reviewer in packet["reviewers"]
            if reviewer["role"] in {"primary_1", "primary_2"}
        }
        first, second = primary["primary_1"], primary["primary_2"]
        for name in RUBRIC_DIMENSIONS:
            adjudicated[name].append(packet["adjudication"]["scores"][name])
            left.append(first["scores"][name])
            right.append(second["scores"][name])
    dimension_means = {
        name: round(sum(values) / len(values), 6)
        for name, values in adjudicated.items()
    }
    overall_mean = round(
        sum(dimension_means.values()) / len(dimension_means), 6
    )
    agreement = round(_quadratic_weighted_kappa(left, right), 6)
    review = config["review"]
    failures = [
        f"DIMENSION_BELOW_MINIMUM:{name}"
        for name, value in dimension_means.items()
        if value < review["minimum_dimension_score"]
    ]
    if overall_mean < review["minimum_overall_score"]:
        failures.append("OVERALL_SCORE_BELOW_MINIMUM")
    if agreement < review["agreement_threshold"]:
        failures.append("REVIEWER_AGREEMENT_BELOW_THRESHOLD")
    return {
        "development_status": "pass" if not failures else "fail",
        "identity_verification": review["identity_verification"],
        "minimum_dimension_score": review["minimum_dimension_score"],
        "minimum_overall_score": review["minimum_overall_score"],
        "dimension_means": dimension_means,
        "overall_mean": overall_mean,
        "agreement_method": review["agreement_method"],
        "agreement": agreement,
        "agreement_threshold": review["agreement_threshold"],
        "failures": failures,
    }


def finalize_session(session: TargetSession) -> dict[str, Any]:
    if session.status != "COMPLETE":
        raise TargetEvaluationError("only a complete session can be finalized")
    run = harness._run_one(
        case=deepcopy(session._case),
        system_id=session.system_id,
        variant=deepcopy(session._variant),
        repetition=session.repetition,
        config={"frozen_at": session._config["frozen_at"], "max_turns": 50},
        provider=_ReplayProvider(session.transcript),
        grader=_ImportedGrader(session.transcript),
        hard_gate_events=set(session._suite["hard_gate_events"]),
    )
    if [turn["turn_id"] for turn in run["transcript"]] != [
        turn["request"]["turn_id"] for turn in session.transcript
    ]:
        raise TargetEvaluationError("replayed turn path differs from captured session")
    for captured in session.transcript:
        for code in captured["review"]["adjudication"]["hard_failure_codes"]:
            failure = {
                "code": code,
                "turn_id": captured["request"]["turn_id"],
                "detail": "human-adjudicated hard failure",
            }
            if failure not in run["failures"]:
                run["failures"].append(failure)
            if failure not in run["hard_failures"]:
                run["hard_failures"].append(failure)
    run["automated_status"] = "pass" if not run["failures"] else "fail"
    run["human_review"] = {
        "status": "pending",
        "required_reviewers": session._case["grader"]["reviewer_count"],
        "received_reviewers": 0,
        "bilingual_required": session._case["grader"]["bilingual_required"],
    }
    reviews = [
        {
            "turn_id": captured["request"]["turn_id"],
            "completion_sha256": captured["completion"]["completion_sha256"],
            "review_sha256": captured["review_sha256"],
            "blinded_run_id": captured["review"]["blinded_run_id"],
            "identity_verification": captured["review"]["identity_verification"],
            "reviewers": deepcopy(captured["review"]["reviewers"]),
            "adjudication": deepcopy(captured["review"]["adjudication"]),
        }
        for captured in session.transcript
    ]
    payload = {
        "schema_version": "1.0",
        "evidence_class": "authored-target-run",
        "qualification_claim_allowed": False,
        "source_commit": session._config["source_commit"],
        "suite_sha256": _digest(session._suite),
        "config_sha256": _digest(session._config),
        "provider_identity_sha256": provider_identity(session._config),
        "run_plan_sha256": _digest(session._config["run_plan"]),
        "planned_run_count": len(session._config["run_plan"]),
        "campaign_complete": False,
        "run": run,
        "captures": [
            {
                "turn_id": captured["request"]["turn_id"],
                "request_sha256": captured["completion"]["request_sha256"],
                "provider_identity_sha256": captured["completion"][
                    "provider_identity_sha256"
                ],
                "provider_response_id": captured["completion"]["provider_response_id"],
                "captured_at": captured["completion"]["captured_at"],
                "completion_sha256": captured["completion"]["completion_sha256"],
            }
            for captured in session.transcript
        ],
        "reviews": reviews,
        "quality": _quality_summary(session.transcript, session._config),
    }
    payload["aggregate_sha256"] = _digest(payload)
    if errors := _schema_errors(payload, TARGET_RESULT_SCHEMA):
        raise TargetEvaluationError("target result schema failure: " + "; ".join(errors))
    result_contract = json.loads(harness.RESULT_SCHEMA.read_text(encoding="utf-8"))
    run_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": result_contract["$defs"],
        **result_contract["$defs"]["run"],
    }
    run_errors = sorted(
        Draft202012Validator(run_schema, format_checker=FormatChecker()).iter_errors(run),
        key=lambda item: list(item.absolute_path),
    )
    if run_errors:
        raise TargetEvaluationError(
            "target run contract failure: "
            + "; ".join(
                f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
                for error in run_errors
            )
        )
    return payload


def target_result_errors(
    artifact: dict[str, Any],
    *,
    suite: dict[str, Any],
    config: dict[str, Any],
    clock: Callable[[], datetime],
) -> list[str]:
    if suite_errors := harness.validate_suite(deepcopy(suite)):
        return ["invalid suite: " + "; ".join(suite_errors)]
    if config_errors := validate_target_config(deepcopy(config), deepcopy(suite)):
        return ["invalid target config: " + "; ".join(config_errors)]
    errors = _schema_errors(artifact, TARGET_RESULT_SCHEMA)
    if errors:
        return errors
    candidate = deepcopy(artifact)
    expected_aggregate = candidate.pop("aggregate_sha256", None)
    if expected_aggregate != _digest(candidate):
        errors.append("aggregate_sha256 mismatch")
        return errors
    if artifact["source_commit"] != config.get("source_commit"):
        errors.append("source_commit mismatch")
    if artifact["suite_sha256"] != _digest(suite):
        errors.append("suite_sha256 mismatch")
    if artifact["config_sha256"] != _digest(config):
        errors.append("config_sha256 mismatch")
    if artifact["provider_identity_sha256"] != provider_identity(config):
        errors.append("provider identity mismatch")
    if artifact["run_plan_sha256"] != _digest(config["run_plan"]):
        errors.append("run_plan_sha256 mismatch")
    if artifact["planned_run_count"] != len(config["run_plan"]):
        errors.append("planned_run_count mismatch")
    if errors:
        return errors
    run = artifact["run"]
    captures = artifact["captures"]
    reviews = artifact["reviews"]
    turns = run.get("transcript", [])
    if not (len(captures) == len(reviews) == len(turns)):
        return ["capture/review/transcript counts differ"]
    response_ids = [capture["provider_response_id"] for capture in captures]
    if len(response_ids) != len(set(response_ids)):
        return ["provider_response_id values are not unique"]
    try:
        session = TargetSession(
            suite=suite,
            config=config,
            case_id=run["case_id"],
            system_id=run["system_id"],
            variant_id=run["variant_id"],
            repetition=run["repetition"],
            clock=clock,
        )
        for run_turn, capture, review in zip(turns, captures, reviews, strict=True):
            request = session.pending_request()
            if (
                request.turn_id != run_turn["turn_id"]
                or request.user != run_turn["user"]
                or request.system_id != run["system_id"]
            ):
                raise TargetEvaluationError("run transcript request path mismatch")
            completion_mapping = {
                "request_sha256": capture["request_sha256"],
                "provider_identity_sha256": capture["provider_identity_sha256"],
                "text": run_turn["assistant"],
                "memory_write_attempted": run_turn["memory_write_attempted"],
                "resource_claims": run_turn["resource_claims"],
                "provider_response_id": capture["provider_response_id"],
                "captured_at": capture["captured_at"],
                "completion_sha256": capture["completion_sha256"],
            }
            completion = _validated_captured_completion(
                completion_mapping, request=request, config=config
            )
            if review["turn_id"] != request.turn_id or review[
                "completion_sha256"
            ] != completion.completion_sha256:
                raise ReviewImportError("turn review is not bound to the completion")
            review_packet = {
                "schema_version": "1.0",
                "completion_sha256": review["completion_sha256"],
                "blinded_run_id": review["blinded_run_id"],
                "identity_verification": review["identity_verification"],
                "reviewers": deepcopy(review["reviewers"]),
                "adjudication": deepcopy(review["adjudication"]),
            }
            if review["review_sha256"] != _digest(review_packet):
                raise ReviewImportError("review_sha256 mismatch")
            session.pending_completion = completion
            session.status = "AWAITING_HUMAN_REVIEW"
            session.import_review(review_packet)
        expected = finalize_session(session)
    except (KeyError, TypeError, ValueError, TargetEvaluationError) as exc:
        return [f"target replay verification failed: {exc}"]
    if expected != artifact:
        errors.append("artifact differs from deterministic target replay")
    return errors


def verify_target_result(
    artifact: dict[str, Any],
    *,
    suite: dict[str, Any],
    config: dict[str, Any],
    clock: Callable[[], datetime],
) -> bool:
    return not target_result_errors(artifact, suite=suite, config=config, clock=clock)
