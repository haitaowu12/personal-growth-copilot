#!/usr/bin/env python3
"""Real-model development campaign with auxiliary, non-qualifying model review."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

import run as harness
import target_session

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "evals/development-config.schema.json"
RESULT_SCHEMA = ROOT / "evals/results/DEVELOPMENT_CAMPAIGN_SCHEMA.json"
REVIEW_OUTPUT_SCHEMA = ROOT / "providers/codex-review-output.schema.json"
RUBRIC_PATH = ROOT / "evals/rubric.md"
REVIEW_PROTOCOL = "pgc-model-review-v1"
RESPONSE_ID = target_session.PROVIDER_RESPONSE_ID


class DevelopmentCampaignError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DevelopmentCampaignError("development campaign clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def schema_errors(value: object, path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def expected_plan(
    suite: dict[str, Any], case_ids: list[str], systems: list[str]
) -> list[dict[str, Any]]:
    cases = set(case_ids)
    return [
        {
            "case_id": case["id"],
            "system_id": system,
            "variant_id": variant["id"],
            "repetition": repetition,
        }
        for case in suite["cases"]
        if case["id"] in cases
        for system in systems
        for variant in case["entry_variants"]
        for repetition in range(1, case["repetitions"] + 1)
    ]


def validate_development_config(
    config: dict[str, Any], suite: dict[str, Any], target_config: dict[str, Any]
) -> list[str]:
    errors = schema_errors(config, CONFIG_SCHEMA)
    if errors:
        return errors
    if harness.validate_suite(suite):
        errors.append("development suite fails canonical validation")
    if target_errors := target_session.validate_target_config(target_config, suite):
        errors.append("target config is invalid: " + "; ".join(target_errors))
    if config["source_commit"] != target_config.get("source_commit"):
        errors.append("development and target configs bind different source commits")
    if config["suite_sha256"] != digest(suite):
        errors.append("development suite hash mismatch")
    if config["target_config_sha256"] != digest(target_config):
        errors.append("development target-config hash mismatch")
    if config["systems"] != [
        item for item in target_config["systems"] if item in set(config["systems"])
    ]:
        errors.append("development systems must retain governed contract order")
    known_cases = [case["id"] for case in suite["cases"]]
    if config["case_ids"] != [
        item for item in known_cases if item in set(config["case_ids"])
    ]:
        errors.append("development cases must retain canonical suite order")
    if config["run_plan"] != expected_plan(
        suite, config["case_ids"], config["systems"]
    ):
        errors.append("development run plan is not the exact selected matrix")
    reviewer = config["reviewer"]
    if reviewer["output_schema_sha256"] != digest(
        json.loads(REVIEW_OUTPUT_SCHEMA.read_text(encoding="utf-8"))
    ):
        errors.append("development reviewer output-schema hash mismatch")
    if reviewer["rubric_sha256"] != file_hash(RUBRIC_PATH):
        errors.append("development reviewer rubric hash mismatch")
    if reviewer["environment_allowlist"] != [
        "PGC_CODEX_AUTH_ROOT",
        "PGC_CODEX_BIN",
    ]:
        errors.append("development reviewer environment allowlist is not exact")
    return errors


def reviewer_identity(config: dict[str, Any]) -> str:
    return digest(
        {
            "source_commit": config["source_commit"],
            "frozen_at": config["frozen_at"],
            "reviewer": config["reviewer"],
        }
    )


def _read_regular(path: Path, maximum: int = 2_097_152) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DevelopmentCampaignError("review adapter is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise DevelopmentCampaignError("review adapter is not a bounded regular file")
        data = b""
        while len(data) <= maximum:
            chunk = os.read(descriptor, min(1_048_576, maximum + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > maximum:
            raise DevelopmentCampaignError("review adapter exceeds its size limit")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise DevelopmentCampaignError("review adapter changed while it was read")
        return data
    finally:
        os.close(descriptor)


class CapturedTargetProvider:
    """Adapt the hash-bound target provider to the generic multi-turn harness."""

    def __init__(self, provider: target_session.FrozenStdioProvider) -> None:
        self.provider = provider
        self.captures: list[dict[str, Any]] = []

    def begin_run(self) -> None:
        self.captures = []

    def complete(self, request: harness.CompletionRequest) -> harness.ModelTurn:
        captured = self.provider.complete(request)
        self.captures.append(
            {
                "request_sha256": captured.request_sha256,
                "provider_identity_sha256": captured.provider_identity_sha256,
                "provider_response_id": captured.provider_response_id,
                "captured_at": captured.captured_at,
                "completion_sha256": captured.completion_sha256,
            }
        )
        return harness.ModelTurn(
            text=captured.text,
            memory_write_attempted=captured.memory_write_attempted,
            resource_claims=tuple(dict(item) for item in captured.resource_claims),
        )


class FrozenAuxiliaryReviewer:
    """Snapshot and invoke a system-blinded auxiliary review adapter."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        suite: dict[str, Any],
        adapter_path: Path,
        environment: Mapping[str, str],
        clock: Callable[[], datetime],
        timeout_seconds: int = 600,
    ) -> None:
        reviewer = config["reviewer"]
        if adapter_path.is_symlink():
            raise DevelopmentCampaignError("review adapter may not be a symlink")
        resolved = adapter_path.resolve(strict=True)
        adapter_bytes = _read_regular(resolved)
        if hashlib.sha256(adapter_bytes).hexdigest() != reviewer["adapter_sha256"]:
            raise DevelopmentCampaignError("review adapter hash mismatch")
        if not os.access(resolved, os.X_OK):
            raise DevelopmentCampaignError("review adapter is not executable")
        allowed = set(reviewer["environment_allowlist"])
        if set(environment) != allowed:
            raise DevelopmentCampaignError(
                "review environment must provide the exact frozen allowlist"
            )
        if not 1 <= timeout_seconds <= 600:
            raise DevelopmentCampaignError("review timeout must be from 1 through 600")
        self.config = deepcopy(config)
        self.suite = deepcopy(suite)
        self.clock = clock
        self.timeout = timeout_seconds
        self.identity_sha256 = reviewer_identity(config)
        self.environment = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "LANG": "C.UTF-8",
            **dict(environment),
        }
        self._temporary = tempfile.TemporaryDirectory(prefix="pgc-review-adapter-")
        self._adapter_path = Path(self._temporary.name) / "adapter"
        descriptor = os.open(
            self._adapter_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o500
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(adapter_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(self._adapter_path, 0o500)
        self._expected_adapter_sha256 = reviewer["adapter_sha256"]
        self._response_ids: set[str] = set()
        self._lock = RLock()
        self._response_lock = Lock()
        self.reviews: list[dict[str, Any]] = []
        self._output_schema = json.loads(
            REVIEW_OUTPUT_SCHEMA.read_text(encoding="utf-8")
        )
        self._rubric = RUBRIC_PATH.read_text(encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None

    def begin_run(self) -> None:
        self.reviews = []

    def _review_request(self, request, output, case, turn) -> dict[str, Any]:
        event_candidates = set(turn["expected_events"]) | set(turn["forbidden_events"])
        for branch in turn.get("branches", []):
            event_candidates.update(branch["when_all"])
            event_candidates.update(branch.get("when_none", []))
        transcript = []
        pairs = list(request.history)
        for index in range(0, len(pairs), 2):
            if index + 1 >= len(pairs):
                break
            transcript.append(
                {
                    "turn_id": f"prior-{index // 2 + 1}",
                    "user": pairs[index][1],
                    "assistant": pairs[index + 1][1],
                }
            )
        transcript.append(
            {
                "turn_id": request.turn_id,
                "user": request.user,
                "assistant": output.text,
            }
        )
        body = {
            "language": case["language"],
            "risk": case["risk"],
            "category": case["category"],
            "current_turn_id": request.turn_id,
            "transcript": transcript,
            "current_observations": {
                "memory_write_attempted": output.memory_write_attempted,
                "resource_claims": [dict(item) for item in output.resource_claims],
            },
            "rubric_dimensions": list(target_session.RUBRIC_DIMENSIONS),
            "event_candidates": sorted(event_candidates),
            "hard_failure_codebook": sorted(
                set(self.suite["hard_gate_events"])
                | target_session.HUMAN_HARD_FAILURE_CODES
            ),
        }
        body["review_request_sha256"] = digest(body)
        return body

    def grade(self, request, output, case, turn) -> harness.TurnGrade:
        with self._lock:
            if self._temporary is None or not self._adapter_path.is_file():
                raise DevelopmentCampaignError("frozen review adapter is unavailable")
            if file_hash(self._adapter_path) != self._expected_adapter_sha256:
                raise DevelopmentCampaignError("frozen review adapter changed")
            review_request = self._review_request(request, output, case, turn)
            reviewer = self.config["reviewer"]
            payload = {
                "protocol": REVIEW_PROTOCOL,
                "reviewer_identity_sha256": self.identity_sha256,
                "reviewer_execution": {
                    "host": reviewer["host"],
                    "model": reviewer["model"],
                    "model_version": reviewer["model_version"],
                    "runtime_executable_sha256": reviewer[
                        "runtime_executable_sha256"
                    ],
                    "output_schema_sha256": reviewer["output_schema_sha256"],
                    "rubric_sha256": reviewer["rubric_sha256"],
                    "settings": deepcopy(reviewer["settings"]),
                    "tool_permissions": list(reviewer["tool_permissions"]),
                },
                "output_schema": deepcopy(self._output_schema),
                "rubric": self._rubric,
                "review_request": review_request,
            }
            request_sha256 = digest(payload)
            result = subprocess.run(
                [str(self._adapter_path)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=self.environment,
                cwd=self._temporary.name,
            )
            if result.returncode != 0:
                raise DevelopmentCampaignError(
                    f"review adapter exited {result.returncode}"
                )
            if len(result.stdout.encode("utf-8")) > 1_048_576:
                raise DevelopmentCampaignError("review adapter stdout exceeds one MiB")
            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise DevelopmentCampaignError(
                    "review adapter stdout is not one JSON value"
                ) from exc
            if not isinstance(response, dict) or set(response) != {
                "protocol",
                "request_sha256",
                "reviewer_identity_sha256",
                "review",
                "provider_response_id",
            }:
                raise DevelopmentCampaignError("review adapter response fields mismatch")
            if (
                response["protocol"] != REVIEW_PROTOCOL
                or response["request_sha256"] != request_sha256
                or response["reviewer_identity_sha256"] != self.identity_sha256
            ):
                raise DevelopmentCampaignError("review adapter response binding mismatch")
            response_id = response["provider_response_id"]
            if not isinstance(response_id, str) or not RESPONSE_ID.fullmatch(response_id):
                raise DevelopmentCampaignError("review response id is malformed")
            with self._response_lock:
                if response_id in self._response_ids:
                    raise DevelopmentCampaignError("review response id was reused")
                self._response_ids.add(response_id)
            review = response["review"]
            if errors := schema_errors(review, REVIEW_OUTPUT_SCHEMA):
                raise DevelopmentCampaignError(
                    "review output schema failure: " + "; ".join(errors)
                )
            if set(review["events"]) - set(review_request["event_candidates"]):
                raise DevelopmentCampaignError("review selected an event outside its codebook")
            if set(review["hard_failure_codes"]) - set(
                review_request["hard_failure_codebook"]
            ):
                raise DevelopmentCampaignError(
                    "review selected a hard failure outside its codebook"
                )
            record = {
                "review_request_sha256": review_request["review_request_sha256"],
                "reviewer_identity_sha256": self.identity_sha256,
                "provider_response_id": response_id,
                **deepcopy(review),
            }
            record["review_sha256"] = digest(record)
            self.reviews.append(record)
            events = tuple(
                sorted(set(review["events"]) | set(review["hard_failure_codes"]))
            )
            return harness.TurnGrade(
                events=events,
                grader_id=self.identity_sha256,
                grader_version=reviewer["adapter_version"],
                method="aux_model",
                resource_claims_reviewed=review["resource_claims_reviewed"],
            )


def run_development_campaign(
    *,
    suite: dict[str, Any],
    target_config: dict[str, Any],
    development_config: dict[str, Any],
    target_provider: CapturedTargetProvider,
    reviewer: FrozenAuxiliaryReviewer,
    source_tree_clean: bool,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    if not source_tree_clean:
        raise DevelopmentCampaignError("development campaign requires a clean tree")
    if errors := validate_development_config(
        development_config, suite, target_config
    ):
        raise DevelopmentCampaignError("invalid development config: " + "; ".join(errors))
    if target_provider.provider.identity_sha256 != target_session.provider_identity(
        target_config
    ):
        raise DevelopmentCampaignError("target provider identity differs from config")
    if reviewer.identity_sha256 != reviewer_identity(development_config):
        raise DevelopmentCampaignError("reviewer identity differs from config")
    started = clock()
    runs: list[dict[str, Any]] = []
    case_by_id = {case["id"]: case for case in suite["cases"]}
    runtime_config = {
        "frozen_at": development_config["frozen_at"],
        "max_turns": development_config["max_turns"],
    }
    for identity in development_config["run_plan"]:
        case = case_by_id[identity["case_id"]]
        variant = next(
            item
            for item in case["entry_variants"]
            if item["id"] == identity["variant_id"]
        )
        target_provider.begin_run()
        reviewer.begin_run()
        result = harness._run_one(
            case=case,
            system_id=identity["system_id"],
            variant=variant,
            repetition=identity["repetition"],
            config=runtime_config,
            provider=target_provider,
            grader=reviewer,
            hard_gate_events=set(suite["hard_gate_events"]),
        )
        runs.append(
            {
                "run_id": result["run_id"],
                "case_id": result["case_id"],
                "system_id": result["system_id"],
                "variant_id": result["variant_id"],
                "repetition": result["repetition"],
                "language": result["language"],
                "risk": result["risk"],
                "automated_status": result["automated_status"],
                "failures": deepcopy(result["failures"]),
                "hard_failures": deepcopy(result["hard_failures"]),
                "transcript": deepcopy(result["transcript"]),
                "transcript_sha256": result["transcript_sha256"],
                "provider_captures": deepcopy(target_provider.captures),
                "auxiliary_reviews": deepcopy(reviewer.reviews),
            }
        )
    finished = clock()
    artifact = {
        "schema_version": "1.0",
        "evidence_class": "model-assisted-development-campaign",
        "qualification_claim_allowed": False,
        "source_commit": development_config["source_commit"],
        "source_tree_clean": True,
        "suite_sha256": digest(suite),
        "target_config_sha256": digest(target_config),
        "development_config_sha256": digest(development_config),
        "provider_identity_sha256": target_provider.provider.identity_sha256,
        "reviewer_identity_sha256": reviewer.identity_sha256,
        "started_at": timestamp(started),
        "finished_at": timestamp(finished),
        "planned_run_count": len(development_config["run_plan"]),
        "completed_run_count": len(runs),
        "summary": {
            "automated_pass": sum(run["automated_status"] == "pass" for run in runs),
            "automated_fail": sum(run["automated_status"] == "fail" for run in runs),
            "hard_failure_runs": sum(bool(run["hard_failures"]) for run in runs),
            "branch_unresolved_runs": sum(
                any(
                    failure["code"] in {"AMBIGUOUS_BRANCH", "BRANCH_UNRESOLVED"}
                    for failure in run["failures"]
                )
                for run in runs
            ),
            "auxiliary_review_count": sum(
                len(run["auxiliary_reviews"]) for run in runs
            ),
        },
        "runs": runs,
        "claim_limit": (
            "This artifact records real target-model executions and system-blinded "
            "auxiliary model reviews for development diagnostics only. Model review "
            "cannot establish reviewer independence, bilingual human integrity, "
            "behavioral qualification, user benefit, privacy readiness, or release approval."
        ),
    }
    artifact["aggregate_sha256"] = digest(artifact)
    if errors := schema_errors(artifact, RESULT_SCHEMA):
        raise DevelopmentCampaignError(
            "development result schema failure: " + "; ".join(errors)
        )
    return artifact


def result_errors(artifact: dict[str, Any]) -> list[str]:
    errors = schema_errors(artifact, RESULT_SCHEMA)
    if errors:
        return errors
    expected = digest(
        {key: value for key, value in artifact.items() if key != "aggregate_sha256"}
    )
    if artifact["aggregate_sha256"] != expected:
        errors.append("development campaign aggregate hash mismatch")
    if artifact["completed_run_count"] != len(artifact["runs"]):
        errors.append("development completed-run count mismatch")
    return errors
