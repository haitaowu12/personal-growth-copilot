#!/usr/bin/env python3
"""Initialize and preflight a private Personal Growth Copilot qualification packet."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402
import release_packet  # noqa: E402
import host_privacy_discovery  # noqa: E402


PLAN_NAME = release_packet.QUALIFICATION_PLAN_NAME
PACKET_DIRECTORIES = (
    "attempts",
    "authorities",
    "behavioral",
    "bilingual",
    "holdout",
    "pilot",
    "privacy",
    "review",
    "target",
)
PLAN_PATHS = {
    "target_config": "target/target-config.json",
    "holdout_seal": "holdout/holdout-seal.json",
    "privacy_host_identity": "privacy/host-identity.json",
    "pilot_protocol": "pilot/protocol.json",
    "authority_roster": "authorities/authority-roster.json",
    "trust_policy": "trust-policy.json",
}
INPUT_LABELS = {
    "target_config": "exact full-suite target config with real reviewer roster",
    "holdout_seal": "independently authored holdout seal and witness key",
    "privacy_host_identity": "named restricted-host identity and audit witness key",
    "pilot_protocol": "preregistered pilot schedule and witness key",
    "authority_roster": "nine independently controlled release authority public keys",
}
INPUT_OWNERS = {
    "target_config": (
        "evaluation owner with the real calibrated reviewer roster",
        "evals/target-config.schema.json plus the exact-source target validator",
    ),
    "holdout_seal": (
        "independent holdout author and holdout witness",
        "release/holdout-seal.schema.json plus ciphertext, schema, authorship, and witness-key replay",
    ),
    "privacy_host_identity": (
        "named-host privacy audit witness",
        "release/privacy-host-identity.schema.json plus audit-key replay",
    ),
    "pilot_protocol": (
        "pilot owner and independently controlled pilot witness",
        "release/pilot-protocol.schema.json plus candidate and witness-key replay",
    ),
    "authority_roster": (
        "nine independently controlled release authorities",
        "exact role roster plus unique Ed25519 path, id, and key-material validation",
    ),
}

PARTICIPANT_REQUIREMENTS = (
    {
        "participant_id": "calibrated_reviewers",
        "minimum_count": 3,
        "responsibility": (
            "Review every governed run while blinded to system identity; the roster "
            "must include at least three reviewers fluent in Chinese or mixed-language review."
        ),
        "independence": (
            "Identity, independence, language fluency, and calibration require external evidence."
        ),
    },
    {
        "participant_id": "holdout_authors",
        "minimum_count": 1,
        "responsibility": "Author and seal untouched cases only after the candidate freeze.",
        "independence": "Candidate authors may not inspect holdout plaintext or author evidence.",
    },
    {
        "participant_id": "holdout_witness",
        "minimum_count": 1,
        "responsibility": "Control the holdout seal and access-audit witness key.",
        "independence": "Key material must be distinct from every other witness and release authority.",
    },
    {
        "participant_id": "privacy_audit_witness",
        "minimum_count": 1,
        "responsibility": "Witness named-host control inventory, findings, and audit completeness.",
        "independence": "Key material must be outside the packet and candidate-author control.",
    },
    {
        "participant_id": "pilot_witness",
        "minimum_count": 1,
        "responsibility": "Preregister and witness the complete 10-20 episode, 28-56 day pilot ledger.",
        "independence": "Key material must be distinct and the episode ledger must be complete.",
    },
    {
        "participant_id": "release_authority_controllers",
        "minimum_count": 9,
        "responsibility": "Control exactly one role-scoped public key for each release gate.",
        "independence": "All nine Ed25519 key identities must be distinct and private keys remain off-packet.",
    },
    {
        "participant_id": "owner",
        "minimum_count": 1,
        "responsibility": "Record the final promotion or decline only after every prerequisite receipt.",
        "independence": "Owner promotion cannot substitute for or precede any other release gate.",
    },
)

HARD_INVARIANTS = (
    "Do not generate, copy, or retain private keys inside the qualification packet.",
    "Do not use model agents or candidate authors as substitutes for required external people or witnesses.",
    "Do not reveal holdout plaintext to candidate authors before execution and access-audit freeze.",
    "Do not retry and retain only favorable target, baseline, holdout, privacy, bilingual, or pilot results.",
    "Do not enable persistence, installation, catalog registration, implicit invocation, or production claims before promotion.",
    "Do not interpret READY_TO_FREEZE, local tests, or this intake contract as release evidence.",
)
def now() -> datetime:
    return datetime.now(timezone.utc)


def _outside_repository(path: Path) -> None:
    root = ROOT.resolve(strict=True)
    if path == root or root in path.parents:
        raise release_evidence.ReleaseEvidenceError(
            "qualification packets must remain outside the source repository"
        )


def _existing_packet_root(path: Path) -> Path:
    if path.is_symlink():
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet root may not be a symlink"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet root is unavailable"
        ) from exc
    if not resolved.is_dir():
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet root must be a directory"
        )
    _outside_repository(resolved)
    return resolved


def _declared_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise release_evidence.ReleaseEvidenceError(
            "qualification plan paths must remain inside the packet"
        )
    candidate = root / relative
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise release_evidence.ReleaseEvidenceError(
            "qualification plan path escaped the packet"
        ) from exc
    return candidate


def _load_plan(root: Path) -> dict[str, Any]:
    plan = release_packet.load_qualification_plan(root)
    for value in plan["paths"].values():
        _declared_path(root, value)
    return plan


def initialize_packet(
    packet_root: Path,
    attempt_campaign_id: str,
    named_host: str,
    environment_id: str,
    *,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    if not isinstance(named_host, str) or not named_host.strip():
        raise release_evidence.ReleaseEvidenceError("named host is required")
    if not isinstance(environment_id, str) or not environment_id.strip():
        raise release_evidence.ReleaseEvidenceError("environment id is required")
    candidate = source_identity(ROOT)
    parent = packet_root.parent.resolve(strict=True)
    root = parent / packet_root.name
    _outside_repository(root)
    if packet_root.exists() or packet_root.is_symlink():
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet initialization is create-only"
        )
    os.mkdir(root, 0o700)
    created_directories: list[Path] = []
    try:
        os.chmod(root, 0o700)
        initialized_at = release_packet.timestamp(clock())
        plan = {
            "schema_version": "1.0",
            "evidence_class": "qualification-packet-plan",
            "status": "DRAFT",
            "candidate_commit": candidate,
            "initialized_at": initialized_at,
            "attempt_campaign_id": attempt_campaign_id,
            "named_host": named_host.strip(),
            "environment_id": environment_id.strip(),
            "storage_root_sha256": host_privacy_discovery.path_identity(root),
            "paths": dict(PLAN_PATHS),
        }
        plan["plan_sha256"] = release_evidence.digest(plan)
        if errors := release_evidence.schema_errors(plan, "qualification_plan"):
            raise release_evidence.ReleaseEvidenceError(
                "invalid qualification packet plan: " + "; ".join(errors)
            )
        for name in PACKET_DIRECTORIES:
            path = root / name
            os.mkdir(path, 0o700)
            os.chmod(path, 0o700)
            created_directories.append(path)
        release_packet.write_private_new(root / PLAN_NAME, plan)
    except Exception:
        for path in reversed(created_directories):
            path.rmdir()
        root.rmdir()
        raise
    return {
        "status": "initialized",
        "candidate_commit": candidate,
        "attempt_campaign_id": attempt_campaign_id,
        "named_host": plan["named_host"],
        "environment_id": plan["environment_id"],
        "storage_root_sha256": plan["storage_root_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "ready_to_freeze": False,
        "missing_inputs": list(INPUT_LABELS),
    }


def preflight_packet(
    packet_root: Path,
    *,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
    input_validator: Callable[..., None] = (
        release_packet.validate_qualification_preregistration_input
    ),
    policy_preparer: Callable[..., dict[str, Any]] = release_packet.prepare_trust_policy,
) -> dict[str, Any]:
    root = _existing_packet_root(packet_root)
    errors: list[str] = []
    missing_inputs: list[str] = []
    invalid_inputs: list[str] = []
    validation_errors: dict[str, list[str]] = {
        input_id: [] for input_id in INPUT_LABELS
    }
    try:
        release_packet.validate_qualification_packet_hygiene(root)
    except release_evidence.ReleaseEvidenceError as exc:
        errors.append(str(exc))
    plan = _load_plan(root)
    try:
        current_candidate = source_identity(ROOT)
    except release_evidence.ReleaseEvidenceError as exc:
        current_candidate = None
        errors.append(str(exc))
    if current_candidate is not None and current_candidate != plan["candidate_commit"]:
        errors.append("qualification plan differs from the exact clean candidate checkout")
    declared = {
        key: _declared_path(root, value) for key, value in plan["paths"].items()
    }
    for input_id in INPUT_LABELS:
        path = declared[input_id]
        if path.is_symlink() or not path.is_file():
            missing_inputs.append(input_id)
            continue
        if errors or current_candidate is None:
            invalid_inputs.append(input_id)
            validation_errors[input_id].append(
                "packet-level validation must pass before this input can be trusted"
            )
            continue
        try:
            input_validator(
                input_id=input_id,
                packet_root=root,
                path=path,
                candidate=current_candidate,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            release_evidence.ReleaseEvidenceError,
        ) as exc:
            invalid_inputs.append(input_id)
            validation_errors[input_id].append(str(exc))
    policy_output = declared["trust_policy"]
    if policy_output.exists() or policy_output.is_symlink():
        errors.append("configured trust-policy output already exists")
    bindings: dict[str, Any] | None = None
    if (
        not errors
        and not missing_inputs
        and not invalid_inputs
        and current_candidate is not None
    ):
        try:
            policy = policy_preparer(
                packet_root=root,
                config_path=declared["target_config"],
                holdout_seal_path=declared["holdout_seal"],
                privacy_host_identity_path=declared["privacy_host_identity"],
                pilot_protocol_path=declared["pilot_protocol"],
                authorities_path=declared["authority_roster"],
                attempt_campaign_id=plan["attempt_campaign_id"],
                candidate=current_candidate,
                frozen=clock(),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            release_evidence.ReleaseEvidenceError,
        ) as exc:
            errors.append(f"trust-policy input validation failed: {exc}")
        else:
            bindings = {
                "qualification_plan_sha256": policy["qualification_plan_sha256"],
                "target_config_sha256": policy["target_config_sha256"],
                "holdout_seal_sha256": policy["holdout_seal_sha256"],
                "privacy_host_identity_sha256": policy[
                    "privacy_host_identity_sha256"
                ],
                "pilot_protocol_sha256": policy["pilot_protocol_sha256"],
                "authority_count": len(policy["authorities"]),
            }
    ready = (
        not errors
        and not missing_inputs
        and not invalid_inputs
        and bindings is not None
    )
    requirements = [
        {
            "input_id": input_id,
            "description": description,
            "path": plan["paths"][input_id],
            "status": (
                "MISSING"
                if input_id in missing_inputs
                else "INVALID"
                if input_id in invalid_inputs
                else "VALID"
            ),
            "validation_errors": validation_errors[input_id],
        }
        for input_id, description in INPUT_LABELS.items()
    ]
    result = {
        "schema_version": "1.0",
        "evidence_class": "qualification-packet-preflight",
        "status": "READY_TO_FREEZE" if ready else "NOT_READY",
        "candidate_commit": plan["candidate_commit"],
        "attempt_campaign_id": plan["attempt_campaign_id"],
        "plan_sha256": plan["plan_sha256"],
        "ready_to_freeze": ready,
        "requirements": requirements,
        "missing_inputs": missing_inputs,
        "invalid_inputs": invalid_inputs,
        "errors": errors,
        "validated_bindings": bindings,
    }
    result["preflight_sha256"] = release_evidence.digest(result)
    return result


def build_external_intake(
    packet_root: Path,
    *,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    """Build a non-evidentiary handoff for the real external qualification roles."""
    root = _existing_packet_root(packet_root)
    plan = _load_plan(root)
    candidate = source_identity(ROOT)
    generated = clock()
    if candidate != plan["candidate_commit"]:
        raise release_evidence.ReleaseEvidenceError(
            "qualification plan differs from the exact clean candidate checkout"
        )
    preflight = preflight_packet(
        root,
        source_identity=lambda _: candidate,
        clock=lambda: generated,
    )
    requirements = {item["input_id"]: item for item in preflight["requirements"]}
    artifact_requirements = [
        {
            "input_id": input_id,
            "path": plan["paths"][input_id],
            "external_owner": INPUT_OWNERS[input_id][0],
            "authority": INPUT_OWNERS[input_id][1],
            "status": requirements[input_id]["status"],
            "validation_errors": requirements[input_id]["validation_errors"],
        }
        for input_id in INPUT_LABELS
    ]
    discovery_path = root / "privacy/host-discovery.json"
    host_remediation: list[dict[str, Any]] = []
    host_discovery: dict[str, Any]
    if discovery_path.is_file() and not discovery_path.is_symlink():
        discovery = release_evidence.json_object(
            release_evidence.read_once(discovery_path), "host privacy discovery"
        )
        if errors := host_privacy_discovery.verify_report(discovery):
            raise release_evidence.ReleaseEvidenceError(
                "invalid host privacy discovery: " + "; ".join(errors)
            )
        if discovery["candidate_commit"] != candidate:
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery differs from the clean candidate checkout"
            )
        if discovery["named_host"] != plan["named_host"]:
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery differs from the qualification host"
            )
        if discovery["environment_id"] != plan["environment_id"]:
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery differs from the qualification environment"
            )
        if discovery["storage_root_sha256"] != plan["storage_root_sha256"]:
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery differs from the qualification storage root"
            )
        discovery_time = release_evidence.parse_time(discovery["generated_at"])
        if discovery_time < release_evidence.parse_time(plan["initialized_at"]):
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery predates the qualification packet"
            )
        if discovery_time > generated:
            raise release_evidence.ReleaseEvidenceError(
                "host privacy discovery may not follow the intake generation time"
            )
        host_discovery = {
            "status": "PRESENT",
            "named_host": discovery["named_host"],
            "environment_id": discovery["environment_id"],
            "generated_at": discovery["generated_at"],
            "report_sha256": discovery["report_sha256"],
            "storage_root_sha256": discovery["storage_root_sha256"],
        }
        host_remediation = [
            {
                "check_id": item["check_id"],
                "status": item["status"],
                "reason_codes": item["reason_codes"],
                "required_outcome": "PASS_IN_SOURCE_WITNESSED_PRIVACY_PREFLIGHT",
            }
            for item in discovery["checks"]
            if item["status"] != "PASS"
        ]
    else:
        host_discovery = {
            "status": "MISSING",
            "named_host": None,
            "environment_id": None,
            "generated_at": None,
            "report_sha256": None,
            "storage_root_sha256": None,
        }
        host_remediation = [
            {
                "check_id": "host_privacy_discovery",
                "status": "MISSING",
                "reason_codes": ["NO_EXACT_CANDIDATE_HOST_DISCOVERY"],
                "required_outcome": "PASS_IN_SOURCE_WITNESSED_PRIVACY_PREFLIGHT",
            }
        ]
    intake = {
        "schema_version": "1.0",
        "evidence_class": "qualification-external-intake",
        "status": "AWAITING_EXTERNAL_INPUTS",
        "candidate_commit": candidate,
        "generated_at": release_packet.timestamp(generated),
        "plan_sha256": plan["plan_sha256"],
        "participant_requirements": list(PARTICIPANT_REQUIREMENTS),
        "artifact_requirements": artifact_requirements,
        "host_discovery": host_discovery,
        "host_remediation": host_remediation,
        "hard_invariants": list(HARD_INVARIANTS),
        "validation_command": (
            f"python scripts/qualification_packet.py preflight --packet-root {root}"
        ),
        "claim_limit": (
            "This is a non-promotional external-participant intake contract. It is "
            "not identity, independence, holdout, host, pilot, gate, or release evidence."
        ),
    }
    intake["intake_sha256"] = release_evidence.digest(intake)
    if errors := release_evidence.schema_errors(intake, "qualification_intake"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid qualification external intake: " + "; ".join(errors)
        )
    return intake


def _intake_output(root: Path, output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise release_evidence.ReleaseEvidenceError(
            "qualification intake output is create-only"
        )
    try:
        parent = output.parent.resolve(strict=True)
        parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise release_evidence.ReleaseEvidenceError(
            "qualification intake output must remain inside the packet"
        ) from exc
    if output.name in {"", ".", ".."} or Path(output.name).name != output.name:
        raise release_evidence.ReleaseEvidenceError(
            "qualification intake output path is not exact"
        )
    return parent / output.name


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--packet-root", type=Path, required=True)
    initialize.add_argument("--attempt-campaign-id", required=True)
    initialize.add_argument("--named-host", required=True)
    initialize.add_argument("--environment-id", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--packet-root", type=Path, required=True)
    intake = commands.add_parser("intake")
    intake.add_argument("--packet-root", type=Path, required=True)
    intake.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            result = initialize_packet(
                args.packet_root,
                args.attempt_campaign_id,
                args.named_host,
                args.environment_id,
            )
        elif args.command == "preflight":
            result = preflight_packet(args.packet_root)
        else:
            root = _existing_packet_root(args.packet_root)
            result = build_external_intake(root)
            release_packet.write_private_new(
                _intake_output(root, args.output), result
            )
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") != "NOT_READY" else 1
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        release_evidence.ReleaseEvidenceError,
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
