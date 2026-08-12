#!/usr/bin/env python3
"""Verify signed, role-scoped Personal Growth Copilot release-gate evidence."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
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
SCHEMAS = {
    "index": ROOT / "release/evidence-index.schema.json",
    "policy": ROOT / "release/trust-policy.schema.json",
    "artifact": ROOT / "release/gate-artifact.schema.json",
    "receipt": ROOT / "release/signed-receipt.schema.json",
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

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
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
            if assertions.get(name) != 0:
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
        if not isinstance(assertions.get("reviewer_count"), int) or assertions["reviewer_count"] < 2:
            errors.append("reviewer attestation requires at least two reviewers")
    elif gate == "attempt_inventory":
        require_true("immutable_inventory", "all_attempts_accounted_for", "submitted_results_complete")
        require_zero("omitted_attempt_count")
        attempts = assertions.get("attempt_count")
        results = assertions.get("submitted_result_count")
        if not isinstance(attempts, int) or not isinstance(results, int) or attempts < results or results < 1:
            errors.append("attempt inventory counts are invalid")
    elif gate == "holdout":
        require_true("sealed", "independent_authors", "all_hard_gates_pass")
        if assertions.get("candidate_author_access") is not False:
            errors.append("holdout candidate-author access must be false")
        fraction = assertions.get("holdout_fraction")
        if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0.20 <= fraction <= 1:
            errors.append("holdout fraction must be at least 0.20")
        if not isinstance(assertions.get("case_count"), int) or assertions["case_count"] < 1:
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
        if not isinstance(assertions.get("fluent_reviewer_count"), int) or assertions["fluent_reviewer_count"] < 2:
            errors.append("bilingual review requires at least two fluent reviewers")
        kappa = assertions.get("minimum_system_kappa")
        if not isinstance(kappa, (int, float)) or isinstance(kappa, bool) or kappa < 0.70:
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
        if not isinstance(episodes, int) or not 10 <= episodes <= 20:
            errors.append("pilot requires 10 through 20 episodes")
        if not isinstance(days, int) or not 28 <= days <= 56:
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


def validate_public_key(public_key: bytes) -> None:
    with tempfile.TemporaryDirectory(prefix="pgc-release-key-") as directory_name:
        key_path = Path(directory_name) / "public.pem"
        key_path.write_bytes(public_key)
        result = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(key_path), "-text", "-noout"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    if result.returncode != 0 or b"ED25519" not in (result.stdout + result.stderr).upper():
        raise ReleaseEvidenceError("trusted public key is not a valid Ed25519 public key")


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
    roles = [item["role"] for item in policy["authorities"]]
    if set(roles) != set(GATE_BY_ROLE) or len(roles) != len(set(roles)):
        errors.append("configured trust policy requires exactly one authority for every gate role")
    trusted_keys: dict[str, bytes] = {}
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
            validate_public_key(public_key)
            trusted_keys[authority["key_id"]] = public_key
        except (OSError, subprocess.SubprocessError, ReleaseEvidenceError) as exc:
            errors.append(f"trust policy authority {authority['key_id']}: {exc}")
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
            if artifact["status"] == "PASS":
                if artifact["hard_failures"]:
                    raise ReleaseEvidenceError("passing gate contains hard failures")
                if assertion_failures := assertion_errors(gate, artifact["assertions"]):
                    raise ReleaseEvidenceError("; ".join(assertion_failures))
            elif not artifact["hard_failures"]:
                raise ReleaseEvidenceError("failed or invalidated gate requires a reason")
            payload = receipt["payload"]
            if payload["gate"] != gate or payload["candidate_commit"] != candidate_commit:
                raise ReleaseEvidenceError("receipt gate or candidate commit mismatch")
            if payload["artifact_sha256"] != artifact["artifact_sha256"]:
                raise ReleaseEvidenceError("receipt is bound to another artifact")
            if payload["outcome"] != artifact["status"]:
                raise ReleaseEvidenceError("receipt outcome differs from artifact status")
            artifact_time = parse_time(artifact["executed_at"])
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
        except (OSError, subprocess.SubprocessError, ReleaseEvidenceError) as exc:
            errors.append(f"{gate}: {exc}")
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
    if derived in {"ELIGIBLE", "PROMOTED"}:
        if derived == "PROMOTED":
            promotion_path = safe_path(index_root, index["gates"]["owner_promotion"]["artifact_path"])
            promotion = json_object(read_once(promotion_path), "owner promotion artifact")
            expected_refs = {artifact_hashes[gate] for gate in GATES[:-1]}
            if set(promotion["evidence_refs"]) != expected_refs:
                errors.append("owner promotion does not reference every prerequisite artifact")
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
        "--repository",
        type=Path,
        default=ROOT,
        help="clean checkout of the exact candidate commit (default: this repository)",
    )
    parser.add_argument(
        "--expected-policy-sha256",
        required=True,
        help="policy hash received from the owner over an independent channel",
    )
    args = parser.parse_args()
    try:
        result = verify(
            args.index,
            args.policy,
            source_identity(args.repository),
            args.expected_policy_sha256,
        )
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
