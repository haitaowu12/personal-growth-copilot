#!/usr/bin/env python3
"""Build canonical create-only release artifacts, receipts, and index versions."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "scripts"))

import campaign  # noqa: E402
import attempt_inventory  # noqa: E402
import release_evidence  # noqa: E402
import target_session  # noqa: E402


def now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise release_evidence.ReleaseEvidenceError(
            "release packet clock must be timezone aware"
        )
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, label: str) -> dict[str, Any]:
    return release_evidence.json_object(release_evidence.read_once(path), label)


def write_private_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = release_evidence.canonical_bytes(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def require_hash(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise release_evidence.ReleaseEvidenceError(f"{label} must be a SHA-256 hash")
    return value


def build_gate_artifact(
    *,
    gate: str,
    candidate_commit: str,
    status: str,
    assertions: dict[str, Any],
    evidence_refs: list[str],
    hard_failures: list[str],
    executed_at: datetime,
    source_manifest: dict[str, str] | None = None,
) -> dict[str, Any]:
    if gate not in release_evidence.GATES:
        raise release_evidence.ReleaseEvidenceError("unknown release gate")
    if status not in {"PASS", "FAIL", "INVALIDATED"}:
        raise release_evidence.ReleaseEvidenceError("invalid release-gate status")
    if (
        not isinstance(candidate_commit, str)
        or len(candidate_commit) != 40
        or any(character not in "0123456789abcdef" for character in candidate_commit)
    ):
        raise release_evidence.ReleaseEvidenceError("candidate commit must be exact")
    if not isinstance(assertions, dict) or not assertions:
        raise release_evidence.ReleaseEvidenceError("gate assertions must be a nonempty object")
    normalized_refs = [require_hash(value, "evidence reference") for value in evidence_refs]
    if not normalized_refs or len(normalized_refs) != len(set(normalized_refs)):
        raise release_evidence.ReleaseEvidenceError(
            "gate evidence references must be nonempty and unique"
        )
    if any(not isinstance(value, str) or not value.strip() for value in hard_failures):
        raise release_evidence.ReleaseEvidenceError("hard-failure reasons must be nonempty")
    if len(hard_failures) != len(set(hard_failures)):
        raise release_evidence.ReleaseEvidenceError("hard-failure reasons must be unique")
    if status == "PASS":
        if hard_failures:
            raise release_evidence.ReleaseEvidenceError(
                "passing gate cannot contain hard failures"
            )
        if errors := release_evidence.assertion_errors(gate, assertions):
            raise release_evidence.ReleaseEvidenceError("; ".join(errors))
    elif not hard_failures:
        raise release_evidence.ReleaseEvidenceError(
            "failed or invalidated gate requires a hard-failure reason"
        )
    artifact = {
        "schema_version": "1.0",
        "gate": gate,
        "candidate_commit": candidate_commit,
        "status": status,
        "executed_at": timestamp(executed_at),
        "hard_failures": list(hard_failures),
        "assertions": deepcopy(assertions),
        "evidence_refs": normalized_refs,
    }
    if source_manifest is not None:
        artifact["source_manifest"] = deepcopy(source_manifest)
    artifact["artifact_sha256"] = release_evidence.digest(artifact)
    if errors := release_evidence.schema_errors(artifact, "artifact"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid gate artifact: " + "; ".join(errors)
        )
    return artifact


def _artifact_from_verified_attempt(
    verification: dict[str, Any], *, candidate_commit: str, executed_at: datetime
) -> dict[str, Any]:
    if (
        verification.get("evidence_class")
        != "externally-witnessed-attempt-inventory"
        or verification.get("verification_status") != "pass"
        or verification.get("inventory_status") != "PASS"
        or verification.get("qualification_ready") is not True
        or verification.get("errors")
        or verification.get("hard_failures")
        or verification.get("candidate_commit") != candidate_commit
    ):
        raise release_evidence.ReleaseEvidenceError(
            "attempt inventory verification is not a passing candidate-bound result"
        )
    if verification.get("inventory_sha256") != release_evidence.object_hash(
        verification, "inventory_sha256"
    ):
        raise release_evidence.ReleaseEvidenceError(
            "attempt inventory verification self-hash mismatch"
        )
    refs = [
        require_hash(verification.get("inventory_sha256"), "inventory hash"),
        require_hash(
            verification.get("provider_access_control_sha256"),
            "provider-access control hash",
        ),
        require_hash(
            verification.get("artifact_inventory_sha256"),
            "artifact-inventory hash",
        ),
        require_hash(
            verification.get("result_manifest_sha256"), "result-manifest hash"
        ),
        require_hash(verification.get("config_sha256"), "target-config hash"),
        require_hash(verification.get("witness_head_sha256"), "witness head hash"),
    ]
    return build_gate_artifact(
        gate="attempt_inventory",
        candidate_commit=candidate_commit,
        status="PASS",
        assertions=verification["assertions"],
        evidence_refs=refs,
        hard_failures=[],
        executed_at=executed_at,
    )


def attempt_artifact(
    *,
    index_path: Path,
    config: dict[str, Any],
    suite: dict[str, Any],
    result_manifest_path: Path,
    policy_path: Path,
    expected_policy_sha256: str,
    expected_head_sha256: str,
    expected_event_count: int,
    candidate_commit: str,
    executed_at: datetime,
    verification_clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    if config.get("source_commit") != candidate_commit:
        raise release_evidence.ReleaseEvidenceError(
            "attempt config differs from the clean candidate checkout"
        )
    verification = attempt_inventory.verify_inventory(
        index_path=index_path,
        config=config,
        suite=suite,
        result_manifest_path=result_manifest_path,
        policy_path=policy_path,
        expected_policy_sha256=expected_policy_sha256,
        expected_head_sha256=expected_head_sha256,
        expected_event_count=expected_event_count,
        clock=verification_clock,
    )
    return _artifact_from_verified_attempt(
        verification,
        candidate_commit=candidate_commit,
        executed_at=executed_at,
    )


def behavioral_artifact(
    aggregate: dict[str, Any],
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    suite: dict[str, Any],
    config: dict[str, Any],
    candidate_commit: str,
    executed_at: datetime,
) -> dict[str, Any]:
    if errors := campaign.campaign_result_errors(
        aggregate,
        manifest=manifest,
        manifest_path=manifest_path,
        suite=suite,
        config=config,
        clock=now,
    ):
        raise release_evidence.ReleaseEvidenceError(
            "campaign result is invalid: " + "; ".join(errors)
        )
    acceptance = aggregate["acceptance"]
    assertions = {
        "submitted_matrix_status": aggregate["behavioral_status"],
        "all_systems_automated_pass": acceptance["all_systems_automated_pass"],
        "all_systems_zero_hard_failures": acceptance[
            "all_systems_zero_hard_failures"
        ],
        "reviewer_agreement_pass": acceptance["reviewer_agreement_pass"],
        "high_critical_scores_pass": acceptance["high_critical_scores_pass"],
        "other_distribution_pass": acceptance["other_distribution_pass"],
        "direct_noninferiority_pass": acceptance["direct_noninferiority_pass"],
        "chinese_integrity_pass": acceptance["chinese_integrity_pass"],
    }
    return build_gate_artifact(
        gate="behavioral_qualification",
        candidate_commit=candidate_commit,
        status="PASS",
        assertions=assertions,
        evidence_refs=[
            aggregate["aggregate_sha256"],
            manifest["manifest_sha256"],
            aggregate["suite_sha256"],
            aggregate["config_sha256"],
            aggregate["run_plan_sha256"],
        ],
        hard_failures=[],
        executed_at=executed_at,
    )


def load_policy(
    policy_path: Path,
    *,
    expected_policy_sha256: str,
    candidate_commit: str,
) -> dict[str, Any]:
    policy = load_json(policy_path, "release trust policy")
    if errors := release_evidence.schema_errors(policy, "policy"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid trust policy: " + "; ".join(errors)
        )
    if (
        release_evidence.object_hash(policy, "policy_sha256")
        != policy["policy_sha256"]
        or policy["policy_sha256"] != expected_policy_sha256
        or policy["status"] != "CONFIGURED"
        or policy["candidate_commit"] != candidate_commit
    ):
        raise release_evidence.ReleaseEvidenceError(
            "trust policy is not configured and externally anchored for the candidate"
        )
    return policy


def build_receipt_payload(
    *, artifact: dict[str, Any], issued_at: datetime, nonce: str
) -> dict[str, Any]:
    if errors := release_evidence.schema_errors(artifact, "artifact"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid gate artifact: " + "; ".join(errors)
        )
    if artifact["artifact_sha256"] != release_evidence.object_hash(
        artifact, "artifact_sha256"
    ):
        raise release_evidence.ReleaseEvidenceError("gate artifact self-hash mismatch")
    if not isinstance(nonce, str) or not 16 <= len(nonce) <= 200:
        raise release_evidence.ReleaseEvidenceError("receipt nonce is invalid")
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise release_evidence.ReleaseEvidenceError(
            "receipt issue time must be timezone aware"
        )
    issued = issued_at.astimezone(timezone.utc)
    if issued < release_evidence.parse_time(artifact["executed_at"]):
        raise release_evidence.ReleaseEvidenceError("receipt cannot predate its artifact")
    payload = {
        "domain": "personal-growth-copilot-release-gate-v1",
        "gate": artifact["gate"],
        "candidate_commit": artifact["candidate_commit"],
        "artifact_sha256": artifact["artifact_sha256"],
        "outcome": artifact["status"],
        "issued_at": timestamp(issued),
        "nonce": nonce,
    }
    probe = {
        "schema_version": "1.0",
        "key_id": "placeholder-key",
        "payload": payload,
        "signature_base64": "A" * 88,
    }
    if errors := release_evidence.schema_errors(probe, "receipt"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid receipt payload: " + "; ".join(errors)
        )
    return payload


def assemble_receipt(
    *,
    payload: dict[str, Any],
    signature: bytes,
    key_id: str,
    policy_path: Path,
    expected_policy_sha256: str,
) -> dict[str, Any]:
    candidate_commit = payload.get("candidate_commit")
    policy = load_policy(
        policy_path,
        expected_policy_sha256=expected_policy_sha256,
        candidate_commit=candidate_commit,
    )
    gate = payload.get("gate")
    matches = [item for item in policy["authorities"] if item["key_id"] == key_id]
    if (
        len(matches) != 1
        or matches[0]["role"] != release_evidence.ROLE_BY_GATE.get(gate)
        or matches[0]["allowed_gates"] != [gate]
    ):
        raise release_evidence.ReleaseEvidenceError(
            "receipt key is not the gate's configured authority"
        )
    authority = matches[0]
    key_path = release_evidence.safe_path(
        policy_path.resolve().parent, authority["public_key_path"]
    )
    public_key = release_evidence.read_once(key_path, maximum=65_536)
    if hashlib.sha256(public_key).hexdigest() != authority["public_key_sha256"]:
        raise release_evidence.ReleaseEvidenceError("receipt public-key hash mismatch")
    release_evidence.validate_public_key(public_key)
    signature_base64 = base64.b64encode(signature).decode("ascii")
    receipt = {
        "schema_version": "1.0",
        "key_id": key_id,
        "payload": deepcopy(payload),
        "signature_base64": signature_base64,
    }
    if errors := release_evidence.schema_errors(receipt, "receipt"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid signed receipt: " + "; ".join(errors)
        )
    release_evidence.verify_signature(payload, signature_base64, public_key)
    return receipt


def _relative_packet_path(root: Path, path: Path) -> str:
    if path.is_symlink():
        raise release_evidence.ReleaseEvidenceError(
            "release packet inputs may not be symlinks"
        )
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise release_evidence.ReleaseEvidenceError(
            "release artifact and receipt must remain in the packet directory"
        ) from exc


def _derived_index_status(gates: dict[str, dict[str, Any]]) -> str:
    statuses = {gate: value["status"] for gate, value in gates.items()}
    if any(value in {"FAIL", "INVALIDATED"} for value in statuses.values()):
        return "BLOCKED"
    if all(statuses[gate] == "PASS" for gate in release_evidence.GATES):
        return "PROMOTED"
    if all(statuses[gate] == "PASS" for gate in release_evidence.GATES[:-1]):
        return "ELIGIBLE"
    return "BLOCKED"


def advance_index(
    *,
    prior_index_path: Path,
    artifact_path: Path,
    receipt_path: Path,
    output_path: Path,
    policy_path: Path,
    expected_policy_sha256: str,
    expected_prior_index_sha256: str,
    candidate_commit: str,
) -> dict[str, Any]:
    prior_result = release_evidence.verify(
        prior_index_path,
        policy_path,
        candidate_commit,
        expected_policy_sha256,
        expected_prior_index_sha256,
    )
    if prior_result["verification_status"] != "pass":
        raise release_evidence.ReleaseEvidenceError(
            "prior release index failed anchored verification: "
            + "; ".join(prior_result["errors"])
        )
    prior = load_json(prior_index_path, "prior evidence index")
    artifact_bytes = release_evidence.read_once(artifact_path)
    receipt_bytes = release_evidence.read_once(receipt_path)
    artifact = release_evidence.json_object(artifact_bytes, "gate artifact")
    receipt = release_evidence.json_object(receipt_bytes, "signed receipt")
    if release_evidence.schema_errors(artifact, "artifact") or release_evidence.schema_errors(
        receipt, "receipt"
    ):
        raise release_evidence.ReleaseEvidenceError(
            "artifact or receipt does not match its release schema"
        )
    gate = artifact["gate"]
    prior_gate_status = prior["gates"][gate]["status"]
    allowed_transition = prior_gate_status == "PENDING" or (
        prior_gate_status == "PASS" and artifact["status"] == "INVALIDATED"
    )
    if not allowed_transition:
        raise release_evidence.ReleaseEvidenceError(
            "release index gate transition is not pending-to-evidence or pass-to-invalidation"
        )
    if (
        artifact["candidate_commit"] != candidate_commit
        or artifact["artifact_sha256"]
        != release_evidence.object_hash(artifact, "artifact_sha256")
        or receipt["payload"]["artifact_sha256"] != artifact["artifact_sha256"]
        or receipt["payload"]["gate"] != gate
        or receipt["payload"]["outcome"] != artifact["status"]
    ):
        raise release_evidence.ReleaseEvidenceError(
            "artifact and receipt bindings do not match"
        )
    root = output_path.resolve().parent
    if root != prior_index_path.resolve().parent:
        raise release_evidence.ReleaseEvidenceError(
            "release index versions must remain in one packet directory"
        )
    gates = deepcopy(prior["gates"])
    gates[gate] = {
        "status": artifact["status"],
        "artifact_path": _relative_packet_path(root, artifact_path),
        "artifact_sha256": artifact["artifact_sha256"],
        "receipt_path": _relative_packet_path(root, receipt_path),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    index = {
        "schema_version": "1.0",
        "candidate_commit": candidate_commit,
        "trust_policy_sha256": prior["trust_policy_sha256"],
        "overall_status": _derived_index_status(gates),
        "gates": gates,
    }
    index["index_sha256"] = release_evidence.digest(index)
    if errors := release_evidence.schema_errors(index, "index"):
        raise release_evidence.ReleaseEvidenceError(
            "new evidence index is invalid: " + "; ".join(errors)
        )
    with tempfile.NamedTemporaryFile(
        prefix=".pgc-index-", suffix=".json", dir=root, delete=False
    ) as stream:
        temporary_path = Path(stream.name)
        stream.write(release_evidence.canonical_bytes(index))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        result = release_evidence.verify(
            temporary_path,
            policy_path,
            candidate_commit,
            expected_policy_sha256,
            index["index_sha256"],
        )
        if result["verification_status"] != "pass":
            raise release_evidence.ReleaseEvidenceError(
                "new release index failed verification: " + "; ".join(result["errors"])
            )
        write_private_new(output_path, index)
    finally:
        temporary_path.unlink(missing_ok=True)
    return index


def _source_commit() -> str:
    return release_evidence.source_identity(ROOT)


def command_attempt(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    suite = load_json(args.suite, "target suite")
    config = load_json(args.config, "target config")
    artifact = attempt_artifact(
        index_path=args.index,
        config=config,
        suite=suite,
        result_manifest_path=args.manifest,
        policy_path=args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
        expected_head_sha256=args.expected_head_sha256,
        expected_event_count=args.expected_event_count,
        candidate_commit=candidate,
        executed_at=now(),
    )
    write_private_new(args.output, artifact)
    print(json.dumps({"status": "pass", "artifact_sha256": artifact["artifact_sha256"]}, indent=2))
    return 0


def command_behavioral(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    suite = load_json(args.suite, "target suite")
    config = load_json(args.config, "target config")
    if config.get("source_commit") != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "target config differs from the clean candidate checkout"
        )
    manifest = load_json(args.manifest, "result manifest")
    aggregate = load_json(args.aggregate, "campaign aggregate")
    artifact = behavioral_artifact(
        aggregate,
        manifest=manifest,
        manifest_path=args.manifest,
        suite=suite,
        config=config,
        candidate_commit=candidate,
        executed_at=now(),
    )
    write_private_new(args.output, artifact)
    print(json.dumps({"status": "pass", "artifact_sha256": artifact["artifact_sha256"]}, indent=2))
    return 0


def command_external(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    assertions = load_json(args.assertions, "gate assertions")
    evidence_refs = list(args.evidence_ref)
    if args.status == "PASS" and args.gate in release_evidence.SOURCE_REPLAY_GATES:
        raise release_evidence.ReleaseEvidenceError(
            "passing external evidence requires build-source-artifact and raw sources"
        )
    if args.gate in {"independent_release_review", "owner_promotion"}:
        if not all(
            (
                args.prior_index,
                args.policy,
                args.expected_policy_sha256,
                args.expected_index_sha256,
            )
        ):
            raise release_evidence.ReleaseEvidenceError(
                "review and owner artifacts require an anchored prior release index"
            )
        verified = release_evidence.verify(
            args.prior_index,
            args.policy,
            candidate,
            args.expected_policy_sha256,
            args.expected_index_sha256,
        )
        if verified["verification_status"] != "pass":
            raise release_evidence.ReleaseEvidenceError(
                "prior release packet verification failed: "
                + "; ".join(verified["errors"])
            )
        index = load_json(args.prior_index, "prior evidence index")
        prerequisites = (
            release_evidence.GATES[:7]
            if args.gate == "independent_release_review"
            else release_evidence.GATES[:-1]
        )
        if any(index["gates"][gate]["status"] != "PASS" for gate in prerequisites):
            raise release_evidence.ReleaseEvidenceError(
                "not every prerequisite gate has verified PASS evidence"
            )
        evidence_refs = [index["gates"][gate]["artifact_sha256"] for gate in prerequisites]
    artifact = build_gate_artifact(
        gate=args.gate,
        candidate_commit=candidate,
        status=args.status,
        assertions=assertions,
        evidence_refs=evidence_refs,
        hard_failures=args.hard_failure,
        executed_at=now(),
    )
    write_private_new(args.output, artifact)
    print(json.dumps({"status": "pass", "artifact_sha256": artifact["artifact_sha256"]}, indent=2))
    return 0


def command_source(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    policy = load_policy(
        args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
        candidate_commit=candidate,
    )
    source_bytes = release_evidence.read_once(args.source)
    source = release_evidence.json_object(source_bytes, "external gate source")
    assertions, errors = release_evidence.verify_external_source(
        args.gate,
        source,
        candidate_commit=candidate,
        frozen_at=release_evidence.parse_time(policy["frozen_at"]),
        source_root=args.source.resolve().parent,
        policy_bindings=policy,
    )
    if errors:
        raise release_evidence.ReleaseEvidenceError(
            "external source verification failed: " + "; ".join(errors)
        )
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    root = args.packet_root.resolve(strict=True)
    source_path = _relative_packet_path(root, args.source)
    executed_at = now()
    completed_field = "ended_at" if args.gate == "pilot" else "completed_at"
    if release_evidence.parse_time(source[completed_field]) > executed_at:
        raise release_evidence.ReleaseEvidenceError(
            "external source completion may not follow its gate artifact"
        )
    artifact = build_gate_artifact(
        gate=args.gate,
        candidate_commit=candidate,
        status="PASS",
        assertions=assertions,
        evidence_refs=[source_sha256],
        hard_failures=[],
        executed_at=executed_at,
        source_manifest={"path": source_path, "sha256": source_sha256},
    )
    write_private_new(args.output, artifact)
    print(
        json.dumps(
            {"status": "pass", "artifact_sha256": artifact["artifact_sha256"]},
            indent=2,
        )
    )
    return 0


def command_policy(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    packet_root = args.packet_root.resolve(strict=True)
    if args.output.parent.resolve() != packet_root:
        raise release_evidence.ReleaseEvidenceError(
            "trust policy output must be directly inside the packet directory"
        )
    suite = load_json(ROOT / "evals/cases.json", "canonical target suite")
    config_bytes = release_evidence.read_once(args.config)
    config = release_evidence.json_object(config_bytes, "target config")
    if config_bytes != release_evidence.canonical_bytes(config):
        raise release_evidence.ReleaseEvidenceError(
            "target config must use canonical JSON bytes"
        )
    if config.get("source_commit") != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "target config differs from the clean candidate checkout"
        )
    if errors := target_session.validate_target_config(config, suite):
        raise release_evidence.ReleaseEvidenceError(
            "invalid target config: " + "; ".join(errors)
        )
    campaign._require_full_suite_scope(suite, config)
    seal = load_json(args.holdout_seal, "holdout seal")
    if errors := release_evidence.schema_errors(seal, "holdout_seal"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid holdout seal: " + "; ".join(errors)
        )
    if seal["seal_sha256"] != release_evidence.object_hash(seal, "seal_sha256"):
        raise release_evidence.ReleaseEvidenceError("holdout seal self-hash mismatch")
    if seal["candidate_commit"] != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "holdout seal differs from the clean candidate checkout"
        )
    for prefix in ("ciphertext", "case_schema"):
        evidence_path = release_evidence.safe_path(
            args.holdout_seal.resolve().parent, seal[f"{prefix}_path"]
        )
        evidence = release_evidence.read_once(evidence_path)
        if hashlib.sha256(evidence).hexdigest() != seal[f"{prefix}_sha256"]:
            raise release_evidence.ReleaseEvidenceError(
                f"holdout {prefix} hash mismatch"
            )
    holdout_witness_key = release_evidence.load_bound_public_key(
        args.holdout_seal.resolve().parent,
        seal["witness_public_key_path"],
        seal["witness_public_key_sha256"],
        "holdout witness",
    )
    authority_document = load_json(args.authorities, "release authority roster")
    if set(authority_document) != {"authorities"} or not isinstance(
        authority_document["authorities"], list
    ):
        raise release_evidence.ReleaseEvidenceError(
            "authority roster must contain only an authorities array"
        )
    authorities: list[dict[str, Any]] = []
    key_identities: list[str] = []
    for item in authority_document["authorities"]:
        if not isinstance(item, dict) or set(item) != {
            "key_id",
            "role",
            "public_key_path",
        }:
            raise release_evidence.ReleaseEvidenceError(
                "each authority requires only key_id, role, and public_key_path"
            )
        role = item["role"]
        if role not in release_evidence.GATE_BY_ROLE:
            raise release_evidence.ReleaseEvidenceError("authority role is invalid")
        public_key_path = release_evidence.safe_path(
            packet_root, item["public_key_path"]
        )
        public_key = release_evidence.read_once(public_key_path, maximum=65_536)
        key_identities.append(release_evidence.validate_public_key(public_key))
        authorities.append(
            {
                "key_id": item["key_id"],
                "role": role,
                "public_key_path": _relative_packet_path(packet_root, public_key_path),
                "public_key_sha256": hashlib.sha256(public_key).hexdigest(),
                "allowed_gates": [release_evidence.GATE_BY_ROLE[role]],
            }
        )
    roles = [item["role"] for item in authorities]
    key_ids = [item["key_id"] for item in authorities]
    key_paths = [item["public_key_path"] for item in authorities]
    if set(roles) != set(release_evidence.GATE_BY_ROLE) or len(roles) != len(
        set(roles)
    ):
        raise release_evidence.ReleaseEvidenceError(
            "authority roster requires exactly one authority for every release role"
        )
    if len(key_ids) != len(set(key_ids)) or len(key_paths) != len(set(key_paths)):
        raise release_evidence.ReleaseEvidenceError(
            "authority key ids and public-key paths must be unique"
        )
    if len(key_identities) != len(set(key_identities)):
        raise release_evidence.ReleaseEvidenceError(
            "release authorities must use distinct Ed25519 key material"
        )
    host_identity = release_evidence.read_once(args.privacy_host_identity)
    host_identity_record = release_evidence.json_object(
        host_identity, "privacy host identity"
    )
    if errors := release_evidence.schema_errors(host_identity_record, "privacy_host"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid privacy host identity: " + "; ".join(errors)
        )
    privacy_witness_key = release_evidence.load_bound_public_key(
        args.privacy_host_identity.resolve().parent,
        host_identity_record["audit_public_key_path"],
        host_identity_record["audit_public_key_sha256"],
        "privacy audit",
    )
    pilot_protocol = release_evidence.read_once(args.pilot_protocol)
    pilot_protocol_record = release_evidence.json_object(
        pilot_protocol, "pilot protocol"
    )
    if errors := release_evidence.schema_errors(
        pilot_protocol_record, "pilot_protocol"
    ):
        raise release_evidence.ReleaseEvidenceError(
            "invalid pilot protocol: " + "; ".join(errors)
        )
    if pilot_protocol_record["candidate_commit"] != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "pilot protocol differs from the clean candidate checkout"
        )
    pilot_witness_key = release_evidence.load_bound_public_key(
        args.pilot_protocol.resolve().parent,
        pilot_protocol_record["witness_public_key_path"],
        pilot_protocol_record["witness_public_key_sha256"],
        "pilot witness",
    )
    witness_key_identities = [
        release_evidence.validate_public_key(key)
        for key in (holdout_witness_key, privacy_witness_key, pilot_witness_key)
    ]
    if len(witness_key_identities) != len(set(witness_key_identities)) or set(
        witness_key_identities
    ) & set(key_identities):
        raise release_evidence.ReleaseEvidenceError(
            "holdout, privacy, pilot, and release authorities require distinct key material"
        )
    frozen = now()
    if release_evidence.parse_time(seal["sealed_at"]) > frozen:
        raise release_evidence.ReleaseEvidenceError(
            "holdout seal may not follow the policy freeze"
        )
    if release_evidence.parse_time(host_identity_record["captured_at"]) > frozen:
        raise release_evidence.ReleaseEvidenceError(
            "privacy host identity may not follow the policy freeze"
        )
    if release_evidence.parse_time(pilot_protocol_record["preregistered_at"]) > frozen:
        raise release_evidence.ReleaseEvidenceError(
            "pilot protocol preregistration may not follow the policy freeze"
        )
    policy = {
        "schema_version": "1.0",
        "status": "CONFIGURED",
        "candidate_commit": candidate,
        "frozen_at": timestamp(frozen),
        "attempt_campaign_id": args.attempt_campaign_id,
        "target_config_sha256": target_session._digest(config),
        "holdout_seal_sha256": seal["seal_sha256"],
        "privacy_host_identity_sha256": hashlib.sha256(host_identity).hexdigest(),
        "pilot_protocol_sha256": hashlib.sha256(pilot_protocol).hexdigest(),
        "authorities": authorities,
    }
    policy["policy_sha256"] = release_evidence.digest(policy)
    if errors := release_evidence.schema_errors(policy, "policy"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid configured trust policy: " + "; ".join(errors)
        )
    write_private_new(args.output, policy)
    print(
        json.dumps(
            {"status": "pass", "policy_sha256": policy["policy_sha256"]},
            indent=2,
        )
    )
    return 0


def command_payload(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    artifact = load_json(args.artifact, "gate artifact")
    if artifact.get("candidate_commit") != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "gate artifact differs from the clean candidate checkout"
        )
    payload = build_receipt_payload(
        artifact=artifact,
        issued_at=now(),
        nonce=args.nonce,
    )
    write_private_new(args.output, payload)
    print(json.dumps({"status": "pass", "payload_sha256": release_evidence.digest(payload)}, indent=2))
    return 0


def command_receipt(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    payload = load_json(args.payload, "receipt payload")
    if payload.get("candidate_commit") != candidate:
        raise release_evidence.ReleaseEvidenceError(
            "receipt payload differs from the clean candidate checkout"
        )
    signature = release_evidence.read_once(args.signature, maximum=4_096)
    receipt = assemble_receipt(
        payload=payload,
        signature=signature,
        key_id=args.key_id,
        policy_path=args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
    )
    write_private_new(args.output, receipt)
    print(json.dumps({"status": "pass", "receipt_sha256": hashlib.sha256(release_evidence.canonical_bytes(receipt)).hexdigest()}, indent=2))
    return 0


def command_advance(args: argparse.Namespace) -> int:
    candidate = _source_commit()
    index = advance_index(
        prior_index_path=args.prior_index,
        artifact_path=args.artifact,
        receipt_path=args.receipt,
        output_path=args.output,
        policy_path=args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
        expected_prior_index_sha256=args.expected_index_sha256,
        candidate_commit=candidate,
    )
    print(json.dumps({"status": "pass", "index_sha256": index["index_sha256"], "overall_status": index["overall_status"]}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    attempt = commands.add_parser("build-attempt-artifact")
    attempt.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
    attempt.add_argument("--config", type=Path, required=True)
    attempt.add_argument("--index", type=Path, required=True)
    attempt.add_argument("--manifest", type=Path, required=True)
    attempt.add_argument("--policy", type=Path, required=True)
    attempt.add_argument("--expected-policy-sha256", required=True)
    attempt.add_argument("--expected-head-sha256", required=True)
    attempt.add_argument("--expected-event-count", type=int, required=True)
    attempt.add_argument("--output", type=Path, required=True)

    behavioral = commands.add_parser("build-behavioral-artifact")
    behavioral.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
    behavioral.add_argument("--config", type=Path, required=True)
    behavioral.add_argument("--manifest", type=Path, required=True)
    behavioral.add_argument("--aggregate", type=Path, required=True)
    behavioral.add_argument("--output", type=Path, required=True)

    policy = commands.add_parser("build-trust-policy")
    policy.add_argument("--packet-root", type=Path, required=True)
    policy.add_argument("--config", type=Path, required=True)
    policy.add_argument("--holdout-seal", type=Path, required=True)
    policy.add_argument("--privacy-host-identity", type=Path, required=True)
    policy.add_argument("--pilot-protocol", type=Path, required=True)
    policy.add_argument("--authorities", type=Path, required=True)
    policy.add_argument("--attempt-campaign-id", required=True)
    policy.add_argument("--output", type=Path, required=True)

    source = commands.add_parser("build-source-artifact")
    source.add_argument(
        "--gate",
        required=True,
        choices=sorted(release_evidence.SOURCE_REPLAY_GATES),
    )
    source.add_argument("--source", type=Path, required=True)
    source.add_argument("--packet-root", type=Path, required=True)
    source.add_argument("--policy", type=Path, required=True)
    source.add_argument("--expected-policy-sha256", required=True)
    source.add_argument("--output", type=Path, required=True)

    external = commands.add_parser("build-external-artifact")
    external.add_argument(
        "--gate",
        required=True,
        choices=[gate for gate in release_evidence.GATES if gate not in {"behavioral_qualification", "attempt_inventory"}],
    )
    external.add_argument("--status", required=True, choices=["PASS", "FAIL", "INVALIDATED"])
    external.add_argument("--assertions", type=Path, required=True)
    external.add_argument("--evidence-ref", action="append", default=[])
    external.add_argument("--hard-failure", action="append", default=[])
    external.add_argument("--prior-index", type=Path)
    external.add_argument("--policy", type=Path)
    external.add_argument("--expected-policy-sha256")
    external.add_argument("--expected-index-sha256")
    external.add_argument("--output", type=Path, required=True)

    payload = commands.add_parser("build-receipt-payload")
    payload.add_argument("--artifact", type=Path, required=True)
    payload.add_argument("--nonce", required=True)
    payload.add_argument("--output", type=Path, required=True)

    receipt = commands.add_parser("assemble-receipt")
    receipt.add_argument("--payload", type=Path, required=True)
    receipt.add_argument("--signature", type=Path, required=True)
    receipt.add_argument("--key-id", required=True)
    receipt.add_argument("--policy", type=Path, required=True)
    receipt.add_argument("--expected-policy-sha256", required=True)
    receipt.add_argument("--output", type=Path, required=True)

    advance = commands.add_parser("advance-index")
    advance.add_argument("--prior-index", type=Path, required=True)
    advance.add_argument("--artifact", type=Path, required=True)
    advance.add_argument("--receipt", type=Path, required=True)
    advance.add_argument("--policy", type=Path, required=True)
    advance.add_argument("--expected-policy-sha256", required=True)
    advance.add_argument("--expected-index-sha256", required=True)
    advance.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return {
            "build-attempt-artifact": command_attempt,
            "build-behavioral-artifact": command_behavioral,
            "build-trust-policy": command_policy,
            "build-source-artifact": command_source,
            "build-external-artifact": command_external,
            "build-receipt-payload": command_payload,
            "assemble-receipt": command_receipt,
            "advance-index": command_advance,
        }[args.command](args)
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
        campaign.CampaignError,
        release_evidence.ReleaseEvidenceError,
        target_session.TargetEvaluationError,
    ) as exc:
        print(
            json.dumps(
                {"status": "fail", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
