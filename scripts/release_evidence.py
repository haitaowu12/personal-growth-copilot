#!/usr/bin/env python3
"""Verify signed, role-scoped Personal Growth Copilot release-gate evidence."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import target_session  # noqa: E402
import campaign  # noqa: E402
SCHEMAS = {
    "index": ROOT / "release/evidence-index.schema.json",
    "policy": ROOT / "release/trust-policy.schema.json",
    "artifact": ROOT / "release/gate-artifact.schema.json",
    "receipt": ROOT / "release/signed-receipt.schema.json",
    "external_source": ROOT / "release/external-gate-source.schema.json",
    "holdout_seal": ROOT / "release/holdout-seal.schema.json",
    "holdout_result": ROOT / "release/holdout-result.schema.json",
    "holdout_attempt": ROOT / "release/holdout-attempt.schema.json",
}
GATES = (
    "behavioral_qualification",
    "reviewer_attestation",
    "attempt_inventory",
    "holdout",
    "privacy_preflight",
    "bilingual_review",
    "pilot",
    "independent_release_review",
    "owner_promotion",
)
ROLE_BY_GATE = {
    "behavioral_qualification": "behavioral_evidence_authority",
    "reviewer_attestation": "reviewer_authority",
    "attempt_inventory": "attempt_log_authority",
    "holdout": "holdout_authority",
    "privacy_preflight": "privacy_authority",
    "bilingual_review": "bilingual_review_authority",
    "pilot": "pilot_authority",
    "independent_release_review": "independent_release_reviewer",
    "owner_promotion": "owner",
}
GATE_BY_ROLE = {role: gate for gate, role in ROLE_BY_GATE.items()}
MAX_CLOCK_SKEW = timedelta(minutes=5)


class ReleaseEvidenceError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def object_hash(value: dict[str, Any], field: str) -> str:
    return digest({key: child for key, child in value.items() if key != field})


def schema_errors(value: object, name: str) -> list[str]:
    schema = json.loads(SCHEMAS[name].read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: "
        f"violates {error.validator}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ReleaseEvidenceError("evidence timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReleaseEvidenceError("evidence timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def safe_path(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise ReleaseEvidenceError("evidence path must remain inside its packet directory")
    candidate = root / value
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ReleaseEvidenceError("evidence path may not traverse a symlink")
        current = current.parent
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ReleaseEvidenceError("evidence path is unavailable") from exc
    if root not in resolved.parents:
        raise ReleaseEvidenceError("evidence path escaped its packet directory")
    return resolved


def read_once(path: Path, maximum: int = 10_485_760) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReleaseEvidenceError("evidence file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ReleaseEvidenceError("evidence must be a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1_048_576, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ReleaseEvidenceError("evidence exceeds its size limit")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ReleaseEvidenceError("evidence changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def json_object(data: bytes, label: str) -> dict[str, Any]:
    def unique_object(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ReleaseEvidenceError(f"{label} contains duplicate JSON keys")
            value[key] = child
        return value

    def reject_constant(_value: str) -> None:
        raise ReleaseEvidenceError(f"{label} contains a non-finite number")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ReleaseEvidenceError(f"{label} contains a non-finite number")
        return parsed

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseEvidenceError(f"{label} must be a JSON object")
    return value


def assertion_errors(gate: str, assertions: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def require_true(*names: str) -> None:
        for name in names:
            if assertions.get(name) is not True:
                errors.append(f"{gate} requires assertions.{name}=true")

    def require_zero(*names: str) -> None:
        for name in names:
            if (
                not isinstance(assertions.get(name), int)
                or isinstance(assertions.get(name), bool)
                or assertions[name] != 0
            ):
                errors.append(f"{gate} requires assertions.{name}=0")

    if gate == "behavioral_qualification":
        if assertions.get("submitted_matrix_status") != "conditional_pass":
            errors.append("behavioral qualification requires conditional submitted-matrix passage")
        require_true(
            "all_systems_automated_pass",
            "all_systems_zero_hard_failures",
            "reviewer_agreement_pass",
            "high_critical_scores_pass",
            "other_distribution_pass",
            "direct_noninferiority_pass",
            "chinese_integrity_pass",
        )
    elif gate == "reviewer_attestation":
        require_true("identities_verified", "independence_verified", "calibration_verified")
        if (
            not isinstance(assertions.get("reviewer_count"), int)
            or isinstance(assertions.get("reviewer_count"), bool)
            or assertions["reviewer_count"] < 2
        ):
            errors.append("reviewer attestation requires at least two reviewers")
    elif gate == "attempt_inventory":
        require_true(
            "immutable_inventory",
            "all_attempts_accounted_for",
            "submitted_results_complete",
            "provider_access_enforced",
            "preregistered_run_plan_bound",
            "external_witness_receipts_verified",
            "all_artifacts_preserved",
        )
        require_zero("omitted_attempt_count")
        attempts = assertions.get("attempt_count")
        results = assertions.get("submitted_result_count")
        if (
            not isinstance(attempts, int)
            or isinstance(attempts, bool)
            or not isinstance(results, int)
            or isinstance(results, bool)
            or attempts < results
            or results < 1
        ):
            errors.append("attempt inventory counts are invalid")
    elif gate == "holdout":
        require_true("sealed", "independent_authors", "all_hard_gates_pass")
        if assertions.get("candidate_author_access") is not False:
            errors.append("holdout candidate-author access must be false")
        fraction = assertions.get("holdout_fraction")
        if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0.20 <= fraction <= 1:
            errors.append("holdout fraction must be at least 0.20")
        if (
            not isinstance(assertions.get("case_count"), int)
            or isinstance(assertions.get("case_count"), bool)
            or assertions["case_count"] < 1
        ):
            errors.append("holdout requires at least one sealed case")
    elif gate == "privacy_preflight":
        require_true(
            "storage_map_verified",
            "encryption_verified",
            "no_sync_verified",
            "backup_restore_verified",
            "correction_export_deletion_verified",
            "bounded_retention_verified",
            "incident_response_tested",
        )
        require_zero("unresolved_high_findings")
        if not isinstance(assertions.get("named_host"), str) or not assertions["named_host"].strip():
            errors.append("privacy preflight requires a named host")
    elif gate == "bilingual_review":
        require_true("human_review_complete", "meaning_preserved", "safety_language_preserved")
        require_zero("meaning_or_safety_failures")
        if (
            not isinstance(assertions.get("fluent_reviewer_count"), int)
            or isinstance(assertions.get("fluent_reviewer_count"), bool)
            or assertions["fluent_reviewer_count"] < 2
        ):
            errors.append("bilingual review requires at least two fluent reviewers")
        kappa = assertions.get("minimum_system_kappa")
        if (
            not isinstance(kappa, (int, float))
            or isinstance(kappa, bool)
            or not math.isfinite(kappa)
            or not 0.70 <= kappa <= 1
        ):
            errors.append("bilingual review requires minimum system kappa >= 0.70")
    elif gate == "pilot":
        require_true("explicit_consent", "withdrawals_honored", "deletion_requests_honored")
        require_zero(
            "privacy_incidents",
            "hard_safety_failures",
            "dependence_failures",
            "fabricated_persistence_failures",
        )
        episodes = assertions.get("episode_count")
        days = assertions.get("duration_days")
        if not isinstance(episodes, int) or isinstance(episodes, bool) or not 10 <= episodes <= 20:
            errors.append("pilot requires 10 through 20 episodes")
        if not isinstance(days, int) or isinstance(days, bool) or not 28 <= days <= 56:
            errors.append("pilot requires 28 through 56 days")
    elif gate == "independent_release_review":
        require_true("scope_complete", "reviewer_independent")
        require_zero("unresolved_findings")
        if assertions.get("decision") != "APPROVE":
            errors.append("independent release review decision must be APPROVE")
    elif gate == "owner_promotion":
        require_true("all_prerequisites_verified")
        if assertions.get("decision") != "PROMOTE":
            errors.append("owner promotion decision must be PROMOTE")
    return errors


SOURCE_REPLAY_GATES = {
    "reviewer_attestation",
    "holdout",
    "privacy_preflight",
    "bilingual_review",
    "pilot",
}


def verify_source_file(
    root: Path,
    relative_path: str,
    expected_sha256: str,
    label: str,
    errors: list[str],
) -> None:
    try:
        path = safe_path(root, relative_path)
        data = read_once(path)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            errors.append(f"{label} hash mismatch")
    except ReleaseEvidenceError as exc:
        errors.append(f"{label}: {exc}")


def verify_external_source(
    gate: str,
    source: dict[str, Any],
    *,
    candidate_commit: str,
    frozen_at: datetime,
    source_root: Path,
    policy_bindings: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors = schema_errors(source, "external_source")
    expected_class = {
        "reviewer_attestation": "reviewer-attestation-source",
        "holdout": "holdout-source",
        "privacy_preflight": "privacy-preflight-source",
        "bilingual_review": "bilingual-review-source",
        "pilot": "pilot-source",
    }.get(gate)
    if expected_class is None or source.get("evidence_class") != expected_class:
        errors.append("external source evidence class does not match its gate")
    if source.get("candidate_commit") != candidate_commit:
        errors.append("external source is not bound to the candidate commit")
    if errors:
        return {}, errors

    def time(field: str) -> datetime:
        value = parse_time(source[field])
        if value < frozen_at:
            errors.append(f"external source {field} predates the frozen trust policy")
        return value

    assertions: dict[str, Any] = {}
    if gate == "reviewer_attestation":
        completed = time("completed_at")
        suite = json_object(read_once(ROOT / "evals/cases.json"), "canonical target suite")
        config_path = safe_path(source_root, source["config_path"])
        manifest_path = safe_path(source_root, source["result_manifest_path"])
        config_bytes = read_once(config_path)
        manifest_bytes = read_once(manifest_path)
        config = json_object(config_bytes, "reviewer source target config")
        if config_bytes != canonical_bytes(config):
            errors.append("reviewer source target config is not canonical JSON")
        if digest(config) != source["config_sha256"]:
            errors.append("reviewer source target-config hash mismatch")
        if source["config_sha256"] != policy_bindings.get("target_config_sha256"):
            errors.append("reviewer target config differs from the owner-frozen policy")
        if hashlib.sha256(manifest_bytes).hexdigest() != source["result_manifest_sha256"]:
            errors.append("reviewer source result-manifest hash mismatch")
        manifest = json_object(manifest_bytes, "reviewer source result manifest")
        if config.get("source_commit") != candidate_commit:
            errors.append("reviewer target config is not candidate-bound")
        if config.get("review", {}).get("rubric_sha256") != source["rubric_sha256"]:
            errors.append("reviewer source rubric hash differs from the target config")
        try:
            results = campaign.load_manifest_results(
                manifest=manifest,
                manifest_path=manifest_path,
                suite=suite,
                config=config,
                clock=lambda: datetime.now(timezone.utc),
            )
        except (campaign.CampaignError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"reviewer result replay failed: {exc}")
            results = []
        actual_counts: dict[str, int] = {}
        first_submission: dict[str, datetime] = {}
        for result in results:
            for review in result["reviews"]:
                for item in review["reviewers"]:
                    reviewer_id = item["reviewer_id"]
                    actual_counts[reviewer_id] = actual_counts.get(reviewer_id, 0) + 1
                    submitted = parse_time(item["submitted_at"])
                    first_submission[reviewer_id] = min(
                        first_submission.get(reviewer_id, submitted), submitted
                    )
        reviewers = source["reviewers"]
        ids = [item["reviewer_id"] for item in reviewers]
        subjects = [item["subject_sha256"] for item in reviewers]
        if len(ids) != len(set(ids)):
            errors.append("reviewer source ids must be unique")
        if len(subjects) != len(set(subjects)):
            errors.append("reviewer source subjects must be unique")
        for item in reviewers:
            for prefix in ("identity", "independence", "calibration"):
                verify_source_file(
                    source_root,
                    item[f"{prefix}_evidence_path"],
                    item[f"{prefix}_evidence_sha256"],
                    f"reviewer {prefix} evidence",
                    errors,
                )
            calibrated = parse_time(item["calibrated_at"])
            if calibrated < frozen_at or calibrated > completed:
                errors.append("reviewer calibration chronology is invalid")
            if item["used_run_count"] != actual_counts.get(item["reviewer_id"], 0):
                errors.append("reviewer source usage count differs from verified results")
            if item["reviewer_id"] in first_submission and calibrated > first_submission[item["reviewer_id"]]:
                errors.append("reviewer calibration follows a submitted qualification review")
        if set(ids) != set(actual_counts):
            errors.append("reviewer source does not cover the exact reviewers used in results")
        roster = {
            item["reviewer_id"]: item
            for item in config.get("review", {}).get("reviewer_roster", [])
        }
        for item in reviewers:
            roster_item = roster.get(item["reviewer_id"])
            if roster_item is None:
                errors.append("reviewer source id is absent from the frozen roster")
                continue
            bindings = {
                "identity_evidence_sha256": "identity_attestation_sha256",
                "independence_evidence_sha256": "independence_attestation_sha256",
                "calibration_evidence_sha256": "calibration_attestation_sha256",
            }
            for source_field, roster_field in bindings.items():
                if item[source_field] != roster_item.get(roster_field):
                    errors.append("reviewer evidence hash differs from the frozen roster")
        assertions = {
            "identities_verified": all(item["identity_verified"] for item in reviewers),
            "independence_verified": all(item["independence_verified"] for item in reviewers),
            "calibration_verified": all(item["calibration_passed"] for item in reviewers),
            "reviewer_count": len(reviewers),
        }
    elif gate == "holdout":
        seal_path = safe_path(source_root, source["seal_path"])
        seal_bytes = read_once(seal_path)
        if hashlib.sha256(seal_bytes).hexdigest() != source["seal_file_sha256"]:
            errors.append("holdout seal file hash mismatch")
        seal = json_object(seal_bytes, "holdout seal")
        errors.extend(schema_errors(seal, "holdout_seal"))
        if seal.get("seal_sha256") != object_hash(seal, "seal_sha256"):
            errors.append("holdout seal self-hash mismatch")
        if seal.get("seal_sha256") != source["seal_sha256"]:
            errors.append("holdout source and seal self-hashes differ")
        if seal.get("seal_sha256") != policy_bindings.get("holdout_seal_sha256"):
            errors.append("holdout seal differs from the owner-frozen policy")
        if seal.get("candidate_commit") != candidate_commit:
            errors.append("holdout seal is not bound to the candidate commit")
        sealed = parse_time(seal["sealed_at"])
        if sealed > frozen_at:
            errors.append("holdout seal follows the frozen trust policy")
        revealed = time("revealed_at")
        completed = time("completed_at")
        if not sealed <= revealed <= completed:
            errors.append("holdout seal/reveal/completion chronology is invalid")
        cases = seal["sealed_case_ids"]
        result_cases = [item["case_id"] for item in source["results"]]
        if sorted(result_cases) != sorted(cases):
            errors.append("holdout results do not cover the exact sealed case set")
        subjects = [item["subject_sha256"] for item in seal["authors"]]
        if len(subjects) != len(set(subjects)):
            errors.append("holdout authors must be distinct subjects")
        for prefix in ("ciphertext", "case_schema"):
            verify_source_file(
                seal_path.parent,
                seal[f"{prefix}_path"],
                seal[f"{prefix}_sha256"],
                f"holdout {prefix} evidence",
                errors,
            )
        verify_source_file(
            source_root,
            source["access_audit_path"],
            source["access_audit_sha256"],
            "holdout access_audit evidence",
            errors,
        )
        for author in seal["authors"]:
            for prefix in ("identity", "independence", "authorship"):
                verify_source_file(
                    seal_path.parent,
                    author[f"{prefix}_evidence_path"],
                    author[f"{prefix}_evidence_sha256"],
                    f"holdout author {prefix} evidence",
                    errors,
                )
        for access in source["candidate_author_access_events"]:
            verify_source_file(
                source_root,
                access["evidence_path"],
                access["evidence_sha256"],
                "holdout candidate-author access evidence",
                errors,
            )
        verified_results: list[dict[str, Any]] = []
        verified_attempts: list[dict[str, Any]] = []
        for reference in source["results"]:
            try:
                result_path = safe_path(source_root, reference["result_path"])
                result_bytes = read_once(result_path)
                if hashlib.sha256(result_bytes).hexdigest() != reference["result_file_sha256"]:
                    errors.append("holdout result file hash mismatch")
                result = json_object(result_bytes, "holdout result")
                errors.extend(schema_errors(result, "holdout_result"))
                if result.get("result_sha256") != object_hash(result, "result_sha256"):
                    errors.append("holdout result self-hash mismatch")
                if result.get("result_sha256") != reference["result_sha256"]:
                    errors.append("holdout result reference self-hash mismatch")
                if result.get("candidate_commit") != candidate_commit or result.get(
                    "case_id"
                ) != reference["case_id"]:
                    errors.append("holdout result candidate or case binding mismatch")
                result_completed = parse_time(result["completed_at"])
                if result_completed < revealed or result_completed > completed:
                    errors.append("holdout result completion chronology is invalid")
                if result.get("automated_status") == "PASS" and result.get(
                    "hard_failure_codes"
                ):
                    errors.append("passing holdout result contains hard failures")
                verified_results.append(result)

                attempt_path = safe_path(
                    source_root, reference["attempt_inventory_path"]
                )
                attempt_bytes = read_once(attempt_path)
                if hashlib.sha256(attempt_bytes).hexdigest() != reference[
                    "attempt_inventory_file_sha256"
                ]:
                    errors.append("holdout attempt-inventory file hash mismatch")
                attempt = json_object(attempt_bytes, "holdout attempt inventory")
                errors.extend(schema_errors(attempt, "holdout_attempt"))
                if attempt.get("attempt_sha256") != object_hash(
                    attempt, "attempt_sha256"
                ):
                    errors.append("holdout attempt inventory self-hash mismatch")
                if attempt.get("attempt_sha256") != reference[
                    "attempt_inventory_sha256"
                ]:
                    errors.append("holdout attempt-inventory reference self-hash mismatch")
                if attempt.get("candidate_commit") != candidate_commit or attempt.get(
                    "case_id"
                ) != reference["case_id"]:
                    errors.append("holdout attempt candidate or case binding mismatch")
                verified_attempts.append(attempt)
            except ReleaseEvidenceError as exc:
                errors.append(f"holdout result replay failed: {exc}")
        fraction = len(cases) / (seal["public_case_count"] + len(cases))
        assertions = {
            "sealed": True,
            "independent_authors": all(item["independence_verified"] for item in seal["authors"]),
            "all_hard_gates_pass": (
                len(verified_results) == len(cases)
                and all(
                    item.get("automated_status") == "PASS"
                    and not item.get("hard_failure_codes")
                    for item in verified_results
                )
                and len(verified_attempts) == len(cases)
                and all(
                    item.get("status") == "PASS"
                    and item.get("all_attempts_accounted_for") is True
                    and item.get("omitted_attempt_count") == 0
                    for item in verified_attempts
                )
            ),
            "candidate_author_access": bool(source["candidate_author_access_events"]),
            "holdout_fraction": fraction,
            "case_count": len(cases),
        }
    elif gate == "privacy_preflight":
        completed = time("completed_at")
        verify_source_file(
            source_root,
            source["host_identity_path"],
            source["host_identity_sha256"],
            "privacy named-host identity evidence",
            errors,
        )
        if source["host_identity_sha256"] != policy_bindings.get(
            "privacy_host_identity_sha256"
        ):
            errors.append("privacy host identity differs from the owner-frozen policy")
        required = {
            "storage_map",
            "encryption",
            "no_sync",
            "backup_restore",
            "correction_export_deletion",
            "bounded_retention",
            "incident_response",
        }
        checks = source["checks"]
        ids = [item["check_id"] for item in checks]
        if len(ids) != len(set(ids)):
            errors.append("privacy control check ids must be unique")
        missing = sorted(required - set(ids))
        if missing:
            errors.append("privacy source is missing required checks: " + ", ".join(missing))
        for item in checks:
            verify_source_file(
                source_root,
                item["evidence_path"],
                item["evidence_sha256"],
                f"privacy {item['check_id']} evidence",
                errors,
            )
            executed = parse_time(item["executed_at"])
            if executed < frozen_at or executed > completed:
                errors.append("privacy check chronology is invalid")
        passed = {item["check_id"]: item["status"] == "PASS" for item in checks}
        unresolved_high = sum(
            item["severity"] in {"high", "critical"} and item["status"] != "RESOLVED"
            for item in source["findings"]
        )
        for finding in source["findings"]:
            verify_source_file(
                source_root,
                finding["evidence_path"],
                finding["evidence_sha256"],
                f"privacy finding {finding['finding_id']} evidence",
                errors,
            )
        assertions = {
            "storage_map_verified": passed.get("storage_map", False),
            "encryption_verified": passed.get("encryption", False),
            "no_sync_verified": passed.get("no_sync", False),
            "backup_restore_verified": passed.get("backup_restore", False),
            "correction_export_deletion_verified": passed.get("correction_export_deletion", False),
            "bounded_retention_verified": passed.get("bounded_retention", False),
            "incident_response_tested": passed.get("incident_response", False),
            "unresolved_high_findings": unresolved_high,
            "named_host": source["named_host"],
        }
    elif gate == "bilingual_review":
        time("completed_at")
        reviewer_path = safe_path(source_root, source["reviewer_source_path"])
        reviewer_bytes = read_once(reviewer_path)
        if hashlib.sha256(reviewer_bytes).hexdigest() != source["reviewer_source_sha256"]:
            errors.append("bilingual reviewer source hash mismatch")
            reviewer_source = {}
        else:
            reviewer_source = json_object(reviewer_bytes, "bilingual reviewer source")
            _, reviewer_errors = verify_external_source(
                "reviewer_attestation",
                reviewer_source,
                candidate_commit=candidate_commit,
                frozen_at=frozen_at,
                source_root=reviewer_path.parent,
                policy_bindings=policy_bindings,
            )
            errors.extend(f"bilingual reviewer source: {item}" for item in reviewer_errors)
        verified_fluent = {
            item["reviewer_id"]
            for item in reviewer_source.get("reviewers", [])
            if {"zh", "mixed"} & set(item["languages"])
        }
        if not set(source["fluent_reviewer_ids"]).issubset(verified_fluent):
            errors.append("bilingual fluent reviewers are not verified by the reviewer source")
        reviews = source["reviews"]
        review_ids = [item["review_id"] for item in reviews]
        if len(review_ids) != len(set(review_ids)) or set(review_ids) != set(source["expected_review_ids"]):
            errors.append("bilingual reviews do not cover the exact expected review set")
        expected_reviews: dict[str, dict[str, Any]] = {}
        try:
            config_path = safe_path(reviewer_path.parent, reviewer_source["config_path"])
            manifest_path = safe_path(reviewer_path.parent, reviewer_source["result_manifest_path"])
            config = json_object(read_once(config_path), "bilingual target config")
            manifest = json_object(read_once(manifest_path), "bilingual result manifest")
            suite = json_object(read_once(ROOT / "evals/cases.json"), "canonical target suite")
            results = campaign.load_manifest_results(
                manifest=manifest,
                manifest_path=manifest_path,
                suite=suite,
                config=config,
                clock=lambda: datetime.now(timezone.utc),
            )
            language_by_case = {item["id"]: item["language"] for item in suite["cases"]}
            for manifest_entry, result in zip(manifest["results"], results, strict=True):
                language = language_by_case[result["run"]["case_id"]]
                if language not in {"zh", "mixed"}:
                    continue
                for review in result["reviews"]:
                    primary = {
                        item["role"]: item
                        for item in review["reviewers"]
                        if item["role"] in {"primary_1", "primary_2"}
                    }
                    failure_codes = sorted(
                        code
                        for code in (
                            list(review["adjudication"]["events"])
                            + list(review["adjudication"]["hard_failure_codes"])
                        )
                        if any(
                            marker in code
                            for marker in campaign.CHINESE_FAILURE_MARKERS
                        )
                    )
                    expected_reviews[review["review_sha256"]] = {
                        "review_id": review["review_sha256"],
                        "run_id": result["run"]["run_id"],
                        "system_id": result["run"]["system_id"],
                        "language": language,
                        "result_sha256": manifest_entry["sha256"],
                        "primary_1_reviewer_id": primary["primary_1"]["reviewer_id"],
                        "primary_2_reviewer_id": primary["primary_2"]["reviewer_id"],
                        "primary_1_scores": primary["primary_1"]["scores"],
                        "primary_2_scores": primary["primary_2"]["scores"],
                        "meaning_or_safety_failure_codes": failure_codes,
                    }
        except (campaign.CampaignError, KeyError, TypeError, ValueError, ReleaseEvidenceError) as exc:
            errors.append(f"bilingual result replay failed: {exc}")
        if set(expected_reviews) != set(source["expected_review_ids"]):
            errors.append("bilingual expected review set differs from verified results")
        for item in reviews:
            if expected_reviews.get(item["review_id"]) != item:
                errors.append("bilingual review record differs from verified result evidence")
        kappas: list[float] = []
        for system in ("target", "direct_assistant", "structured_reflection"):
            left: list[int] = []
            right: list[int] = []
            for item in reviews:
                if item["system_id"] != system:
                    continue
                if not {
                    item["primary_1_reviewer_id"],
                    item["primary_2_reviewer_id"],
                }.issubset(set(source["fluent_reviewer_ids"])):
                    errors.append("bilingual run uses a reviewer without verified fluency")
                if set(item["primary_1_scores"]) != set(item["primary_2_scores"]):
                    errors.append("bilingual primary score dimensions differ")
                    continue
                for dimension in sorted(item["primary_1_scores"]):
                    left.append(item["primary_1_scores"][dimension])
                    right.append(item["primary_2_scores"][dimension])
            measured = target_session._quadratic_weighted_kappa(left, right) if left else None
            if measured is None:
                errors.append(f"bilingual agreement is not estimable for {system}")
            else:
                kappas.append(measured)
        failure_count = sum(len(item["meaning_or_safety_failure_codes"]) for item in reviews)
        assertions = {
            "human_review_complete": set(review_ids) == set(source["expected_review_ids"]),
            "meaning_preserved": failure_count == 0,
            "safety_language_preserved": failure_count == 0,
            "meaning_or_safety_failures": failure_count,
            "fluent_reviewer_count": len(set(source["fluent_reviewer_ids"])),
            "minimum_system_kappa": min(kappas) if len(kappas) == 3 else -1,
        }
    elif gate == "pilot":
        preregistered = time("preregistered_at")
        started = time("started_at")
        ended = time("ended_at")
        if not preregistered <= started <= ended:
            errors.append("pilot preregistration/start/end chronology is invalid")
        verify_source_file(
            source_root,
            source["protocol_path"],
            source["protocol_sha256"],
            "pilot protocol evidence",
            errors,
        )
        if source["protocol_sha256"] != policy_bindings.get("pilot_protocol_sha256"):
            errors.append("pilot protocol differs from the owner-frozen policy")
        planned = source["planned_episode_ids"]
        episode_ids = [item["episode_id"] for item in source["episodes"]]
        if len(episode_ids) != len(set(episode_ids)) or set(episode_ids) != set(planned):
            errors.append("pilot episodes do not cover the exact preregistered schedule")
        withdrawals_honored = True
        deletions_honored = True
        consent = True
        for item in source["episodes"]:
            verify_source_file(
                source_root,
                item["consent_evidence_path"],
                item["consent_evidence_sha256"],
                "pilot consent evidence",
                errors,
            )
            verify_source_file(
                source_root,
                item["episode_evidence_path"],
                item["episode_evidence_sha256"],
                "pilot episode evidence",
                errors,
            )
            scheduled = parse_time(item["scheduled_at"])
            closed = parse_time(item["closed_at"])
            if scheduled < started or closed < scheduled or closed > ended:
                errors.append("pilot episode chronology is invalid")
            requested = item["withdrawal_requested_at"]
            honored = item["withdrawal_honored_at"]
            if item["outcome"] == "WITHDRAWN" and requested is None:
                withdrawals_honored = False
            if (requested is None) != (honored is None):
                withdrawals_honored = False
            elif requested is not None and parse_time(honored) < parse_time(requested):
                withdrawals_honored = False
            if item["deletion_requested"] != (item["deletion_completed_at"] is not None):
                deletions_honored = False
            consent = consent and bool(item["consent_evidence_sha256"])
        categories = [item["category"] for item in source["incidents"]]
        for incident in source["incidents"]:
            verify_source_file(
                source_root,
                incident["evidence_path"],
                incident["evidence_sha256"],
                f"pilot incident {incident['incident_id']} evidence",
                errors,
            )
        duration = (ended.date() - started.date()).days
        assertions = {
            "explicit_consent": consent,
            "withdrawals_honored": withdrawals_honored,
            "deletion_requests_honored": deletions_honored,
            "privacy_incidents": categories.count("privacy"),
            "hard_safety_failures": categories.count("hard_safety"),
            "dependence_failures": categories.count("dependence"),
            "fabricated_persistence_failures": categories.count("fabricated_persistence"),
            "episode_count": len(source["episodes"]),
            "duration_days": duration,
        }
    errors.extend(assertion_errors(gate, assertions))
    return assertions, errors


def verify_signature(payload: dict[str, Any], signature: str, public_key: bytes) -> None:
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ReleaseEvidenceError("receipt signature is not canonical base64") from exc
    with tempfile.TemporaryDirectory(prefix="pgc-release-receipt-") as directory_name:
        directory = Path(directory_name)
        key_path = directory / "public.pem"
        payload_path = directory / "payload.json"
        signature_path = directory / "signature.bin"
        key_path.write_bytes(public_key)
        payload_path.write_bytes(canonical_bytes(payload))
        signature_path.write_bytes(signature_bytes)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(key_path),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    if result.returncode != 0:
        raise ReleaseEvidenceError("receipt signature verification failed")


def validate_public_key(public_key: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="pgc-release-key-") as directory_name:
        key_path = Path(directory_name) / "public.pem"
        key_path.write_bytes(public_key)
        description = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(key_path), "-text", "-noout"],
            capture_output=True,
            check=False,
            timeout=30,
        )
        canonical = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(key_path), "-pubout", "-outform", "DER"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    if (
        description.returncode != 0
        or canonical.returncode != 0
        or b"ED25519" not in (description.stdout + description.stderr).upper()
    ):
        raise ReleaseEvidenceError("trusted public key is not a valid Ed25519 public key")
    return hashlib.sha256(canonical.stdout).hexdigest()


def source_identity(repository: Path) -> str:
    repository = repository.resolve(strict=True)
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            check=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository,
            capture_output=True,
            check=True,
            text=True,
            timeout=30,
        ).stdout
    except subprocess.SubprocessError as exc:
        raise ReleaseEvidenceError("candidate source identity is unavailable") from exc
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise ReleaseEvidenceError("candidate source commit is invalid")
    if status:
        raise ReleaseEvidenceError("candidate source tree must be clean")
    return head


def verify(
    index_path: Path,
    policy_path: Path,
    expected_commit: str,
    expected_policy_sha256: str,
    expected_index_sha256: str,
) -> dict[str, Any]:
    index_root = index_path.resolve().parent
    policy_root = policy_path.resolve().parent
    index = json_object(read_once(index_path), "evidence index")
    policy = json_object(read_once(policy_path), "trust policy")
    errors = schema_errors(index, "index") + schema_errors(policy, "policy")
    if errors:
        return {
            "verification_status": "fail",
            "release_status": "BLOCKED",
            "candidate_commit": index.get("candidate_commit"),
            "verified_gate_count": 0,
            "qualification_update_allowed": False,
            "errors": errors,
        }
    verification_time = datetime.now(timezone.utc)
    if object_hash(index, "index_sha256") != index["index_sha256"]:
        errors.append("evidence index self-hash mismatch")
    if (
        not isinstance(expected_index_sha256, str)
        or len(expected_index_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_index_sha256)
        or index["index_sha256"] != expected_index_sha256
    ):
        errors.append("evidence index does not match the out-of-band current-state anchor")
    if object_hash(policy, "policy_sha256") != policy["policy_sha256"]:
        errors.append("trust policy self-hash mismatch")
    if (
        not isinstance(expected_policy_sha256, str)
        or len(expected_policy_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_policy_sha256)
        or policy["policy_sha256"] != expected_policy_sha256
    ):
        errors.append("trust policy does not match the out-of-band owner trust anchor")
    if index["trust_policy_sha256"] != policy["policy_sha256"]:
        errors.append("evidence index is not bound to the trust policy")
    if policy["status"] != "CONFIGURED":
        errors.append("trust policy is unconfigured")
    if index["candidate_commit"] != policy["candidate_commit"]:
        errors.append("index and trust policy candidate commits differ")
    candidate_commit = index["candidate_commit"]
    if candidate_commit != expected_commit:
        errors.append("release packet is not bound to the checked-out candidate commit")
    authorities = {item["key_id"]: item for item in policy["authorities"]}
    if len(authorities) != len(policy["authorities"]):
        errors.append("trust policy key ids must be unique")
    public_key_hashes = [item["public_key_sha256"] for item in policy["authorities"]]
    if len(public_key_hashes) != len(set(public_key_hashes)):
        errors.append("trust policy authority public keys must be unique")
    public_key_paths = [item["public_key_path"] for item in policy["authorities"]]
    if len(public_key_paths) != len(set(public_key_paths)):
        errors.append("trust policy authority public-key paths must be unique")
    roles = [item["role"] for item in policy["authorities"]]
    if set(roles) != set(GATE_BY_ROLE) or len(roles) != len(set(roles)):
        errors.append("configured trust policy requires exactly one authority for every gate role")
    trusted_keys: dict[str, bytes] = {}
    canonical_key_identities: list[str] = []
    for authority in policy["authorities"]:
        expected_gate = GATE_BY_ROLE[authority["role"]]
        if authority["allowed_gates"] != [expected_gate]:
            errors.append(
                f"trust policy authority {authority['key_id']} must be scoped only to {expected_gate}"
            )
        try:
            public_key_path = safe_path(policy_root, authority["public_key_path"])
            public_key = read_once(public_key_path, maximum=65_536)
            if hashlib.sha256(public_key).hexdigest() != authority["public_key_sha256"]:
                raise ReleaseEvidenceError("trusted public key hash mismatch")
            canonical_key_identities.append(validate_public_key(public_key))
            trusted_keys[authority["key_id"]] = public_key
        except (OSError, subprocess.SubprocessError, ReleaseEvidenceError) as exc:
            errors.append(f"trust policy authority {authority['key_id']}: {exc}")
    if len(canonical_key_identities) != len(set(canonical_key_identities)):
        errors.append("trust policy authorities must use distinct Ed25519 key material")
    frozen_at: datetime | None = None
    if policy["status"] == "CONFIGURED":
        try:
            frozen_at = parse_time(policy["frozen_at"])
            if frozen_at > verification_time + MAX_CLOCK_SKEW:
                errors.append("trust policy freeze time may not be in the future")
        except ReleaseEvidenceError as exc:
            errors.append(f"trust policy: {exc}")
    gate_status: dict[str, str] = {}
    artifact_hashes: dict[str, str] = {}
    verified_artifacts: dict[str, dict[str, Any]] = {}
    artifact_times: dict[str, datetime] = {}
    receipt_times: dict[str, datetime] = {}
    receipt_nonces: set[str] = set()
    for gate in GATES:
        reference = index["gates"][gate]
        gate_status[gate] = reference["status"]
        if reference["status"] == "PENDING":
            if any(reference[field] is not None for field in ("artifact_path", "artifact_sha256", "receipt_path", "receipt_sha256")):
                errors.append(f"{gate}: pending evidence may not contain artifact or receipt claims")
            continue
        if any(reference[field] is None for field in ("artifact_path", "artifact_sha256", "receipt_path", "receipt_sha256")):
            errors.append(f"{gate}: non-pending evidence requires artifact and receipt bindings")
            continue
        try:
            artifact_path = safe_path(index_root, reference["artifact_path"])
            receipt_path = safe_path(index_root, reference["receipt_path"])
            artifact_bytes = read_once(artifact_path)
            receipt_bytes = read_once(receipt_path)
            if hashlib.sha256(receipt_bytes).hexdigest() != reference["receipt_sha256"]:
                raise ReleaseEvidenceError("receipt file hash mismatch")
            artifact = json_object(artifact_bytes, "gate artifact")
            receipt = json_object(receipt_bytes, "signed receipt")
            gate_errors = schema_errors(artifact, "artifact") + schema_errors(receipt, "receipt")
            if gate_errors:
                raise ReleaseEvidenceError("; ".join(gate_errors))
            if artifact["artifact_sha256"] != object_hash(artifact, "artifact_sha256"):
                raise ReleaseEvidenceError("artifact self-hash mismatch")
            if artifact["artifact_sha256"] != reference["artifact_sha256"]:
                raise ReleaseEvidenceError("index artifact hash differs from artifact self-hash")
            if artifact["gate"] != gate or artifact["candidate_commit"] != candidate_commit:
                raise ReleaseEvidenceError("artifact gate or candidate commit mismatch")
            if reference["status"] != artifact["status"]:
                raise ReleaseEvidenceError("index gate status differs from artifact status")
            artifact_time = parse_time(artifact["executed_at"])
            if artifact["status"] == "PASS":
                if artifact["hard_failures"]:
                    raise ReleaseEvidenceError("passing gate contains hard failures")
                if assertion_failures := assertion_errors(gate, artifact["assertions"]):
                    raise ReleaseEvidenceError("; ".join(assertion_failures))
                if gate in {"behavioral_qualification", "attempt_inventory"} and policy[
                    "target_config_sha256"
                ] not in artifact["evidence_refs"]:
                    raise ReleaseEvidenceError(
                        f"{gate} is not bound to the owner-frozen target config"
                    )
                if gate in SOURCE_REPLAY_GATES:
                    if frozen_at is None:
                        raise ReleaseEvidenceError(
                            "configured policy has no valid freeze timestamp"
                        )
                    source_reference = artifact.get("source_manifest")
                    if not isinstance(source_reference, dict):
                        raise ReleaseEvidenceError(
                            "passing external gate requires replayable source evidence"
                        )
                    source_path = safe_path(index_root, source_reference["path"])
                    source_bytes = read_once(source_path)
                    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
                    if source_sha256 != source_reference["sha256"]:
                        raise ReleaseEvidenceError("external source file hash mismatch")
                    if source_sha256 not in artifact["evidence_refs"]:
                        raise ReleaseEvidenceError(
                            "external source hash is absent from artifact evidence references"
                        )
                    source = json_object(source_bytes, "external gate source")
                    replayed_assertions, source_errors = verify_external_source(
                        gate,
                        source,
                        candidate_commit=candidate_commit,
                        frozen_at=frozen_at,
                        source_root=source_path.parent,
                        policy_bindings=policy,
                    )
                    if source_errors:
                        raise ReleaseEvidenceError("; ".join(source_errors))
                    if replayed_assertions != artifact["assertions"]:
                        raise ReleaseEvidenceError(
                            "external gate assertions differ from source replay"
                        )
                    completed_field = "ended_at" if gate == "pilot" else "completed_at"
                    if parse_time(source[completed_field]) > artifact_time:
                        raise ReleaseEvidenceError(
                            "external source completion follows its gate artifact"
                        )
            elif not artifact["hard_failures"]:
                raise ReleaseEvidenceError("failed or invalidated gate requires a reason")
            payload = receipt["payload"]
            if payload["gate"] != gate or payload["candidate_commit"] != candidate_commit:
                raise ReleaseEvidenceError("receipt gate or candidate commit mismatch")
            if payload["artifact_sha256"] != artifact["artifact_sha256"]:
                raise ReleaseEvidenceError("receipt is bound to another artifact")
            if payload["outcome"] != artifact["status"]:
                raise ReleaseEvidenceError("receipt outcome differs from artifact status")
            receipt_time = parse_time(payload["issued_at"])
            if frozen_at is not None and artifact_time < frozen_at:
                raise ReleaseEvidenceError("artifact predates the frozen trust policy")
            if receipt_time < artifact_time:
                raise ReleaseEvidenceError("receipt predates its artifact")
            if (
                artifact_time > verification_time + MAX_CLOCK_SKEW
                or receipt_time > verification_time + MAX_CLOCK_SKEW
            ):
                raise ReleaseEvidenceError("artifact or receipt time may not be in the future")
            if payload["nonce"] in receipt_nonces:
                raise ReleaseEvidenceError("receipt nonce was reused")
            receipt_nonces.add(payload["nonce"])
            authority = authorities.get(receipt["key_id"])
            if authority is None:
                raise ReleaseEvidenceError("receipt key is absent from the trust policy")
            if authority["role"] != ROLE_BY_GATE[gate] or gate not in authority["allowed_gates"]:
                raise ReleaseEvidenceError("receipt authority is not permitted for this gate")
            public_key = trusted_keys.get(receipt["key_id"])
            if public_key is None:
                raise ReleaseEvidenceError("receipt authority key did not pass trust-policy validation")
            verify_signature(payload, receipt["signature_base64"], public_key)
            artifact_hashes[gate] = artifact["artifact_sha256"]
            verified_artifacts[gate] = artifact
            artifact_times[gate] = artifact_time
            receipt_times[gate] = receipt_time
        except (OSError, subprocess.SubprocessError, ReleaseEvidenceError) as exc:
            errors.append(f"{gate}: {exc}")
    review_gate = "independent_release_review"
    review_prerequisites = GATES[:7]
    if gate_status.get(review_gate) == "PASS" and review_gate in verified_artifacts:
        if not all(gate in artifact_hashes for gate in review_prerequisites):
            errors.append("independent release review lacks verified prerequisite gates")
        else:
            expected_refs = {artifact_hashes[gate] for gate in review_prerequisites}
            if set(verified_artifacts[review_gate]["evidence_refs"]) != expected_refs:
                errors.append("independent release review does not reference every prior gate")
            if artifact_times[review_gate] < max(
                receipt_times[gate] for gate in review_prerequisites
            ):
                errors.append("independent release review predates prerequisite receipts")
    owner_gate = "owner_promotion"
    owner_prerequisites = GATES[:-1]
    if gate_status.get(owner_gate) == "PASS" and owner_gate in verified_artifacts:
        if not all(gate in artifact_hashes for gate in owner_prerequisites):
            errors.append("owner promotion lacks verified prerequisite gates")
        else:
            expected_refs = {artifact_hashes[gate] for gate in owner_prerequisites}
            if set(verified_artifacts[owner_gate]["evidence_refs"]) != expected_refs:
                errors.append("owner promotion does not reference every prerequisite artifact")
            if artifact_times[owner_gate] < max(
                receipt_times[gate] for gate in owner_prerequisites
            ):
                errors.append("owner promotion predates prerequisite receipts")
    pass_gates = {gate for gate, status in gate_status.items() if status == "PASS" and gate in artifact_hashes}
    prerequisites = set(GATES[:-1])
    derived = "BLOCKED"
    has_signed_failure = any(
        status in {"FAIL", "INVALIDATED"} for status in gate_status.values()
    )
    if not has_signed_failure and prerequisites.issubset(pass_gates):
        derived = "ELIGIBLE"
        if gate_status["owner_promotion"] == "PASS" and "owner_promotion" in artifact_hashes:
            derived = "PROMOTED"
    if index["overall_status"] != derived:
        errors.append(f"declared overall status {index['overall_status']} differs from derived {derived}")
    if errors:
        derived = "BLOCKED"
    return {
        "verification_status": "pass" if not errors else "fail",
        "release_status": derived,
        "candidate_commit": candidate_commit,
        "verified_gate_count": len(artifact_hashes),
        "qualification_update_allowed": derived == "PROMOTED" and not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument(
        "--expected-policy-sha256",
        required=True,
        help="policy hash received from the owner over an independent channel",
    )
    parser.add_argument(
        "--expected-index-sha256",
        required=True,
        help="current evidence-index hash received from the owner over an independent channel",
    )
    args = parser.parse_args()
    try:
        expected_commit = source_identity(ROOT)
        result = verify(
            args.index,
            args.policy,
            expected_commit,
            args.expected_policy_sha256,
            args.expected_index_sha256,
        )
        if source_identity(ROOT) != expected_commit:
            result["verification_status"] = "fail"
            result["release_status"] = "BLOCKED"
            result["qualification_update_allowed"] = False
            result["errors"].append("candidate source changed during verification")
    except (OSError, subprocess.SubprocessError, ReleaseEvidenceError) as exc:
        result = {
            "verification_status": "fail",
            "release_status": "BLOCKED",
            "candidate_commit": None,
            "verified_gate_count": 0,
            "qualification_update_allowed": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    print(json.dumps(result, indent=2))
    return 0 if result["verification_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
