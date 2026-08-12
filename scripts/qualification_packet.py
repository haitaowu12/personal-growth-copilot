#!/usr/bin/env python3
"""Initialize and preflight a private Personal Growth Copilot qualification packet."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402
import release_packet  # noqa: E402


PLAN_NAME = "qualification-plan.json"
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
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
)
MAX_PACKET_FILES = 10_000
MAX_PREFLIGHT_FILE_BYTES = 10_485_760


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


def _require_private_mode(path: Path, *, directory: bool) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet may not contain symlinks"
        )
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(metadata.st_mode):
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet may contain only regular files and directories"
        )
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet paths may not grant group or other access"
        )


def _scan_packet(root: Path) -> None:
    count = 0
    _require_private_mode(root, directory=True)
    for directory_name, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        directory = Path(directory_name)
        for name in directory_names:
            count += 1
            _require_private_mode(directory / name, directory=True)
        for name in file_names:
            count += 1
            path = directory / name
            _require_private_mode(path, directory=False)
            data = release_evidence.read_once(
                path, maximum=MAX_PREFLIGHT_FILE_BYTES
            )
            if any(marker in data for marker in PRIVATE_KEY_MARKERS):
                raise release_evidence.ReleaseEvidenceError(
                    "qualification packet contains PEM private-key material"
                )
        if count > MAX_PACKET_FILES:
            raise release_evidence.ReleaseEvidenceError(
                "qualification packet exceeds the preflight file-count limit"
            )


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
    plan_path = root / PLAN_NAME
    plan_bytes = release_evidence.read_once(plan_path)
    plan = release_evidence.json_object(plan_bytes, "qualification packet plan")
    if plan_bytes != release_evidence.canonical_bytes(plan):
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet plan must use canonical JSON bytes"
        )
    if errors := release_evidence.schema_errors(plan, "qualification_plan"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid qualification packet plan: " + "; ".join(errors)
        )
    if plan["plan_sha256"] != release_evidence.object_hash(plan, "plan_sha256"):
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet plan self-hash mismatch"
        )
    if len(set(plan["paths"].values())) != len(plan["paths"]):
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet plan paths must be unique"
        )
    for value in plan["paths"].values():
        _declared_path(root, value)
    return plan


def initialize_packet(
    packet_root: Path,
    attempt_campaign_id: str,
    *,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
) -> dict[str, Any]:
    candidate = source_identity(ROOT)
    parent = packet_root.parent.resolve(strict=True)
    root = parent / packet_root.name
    _outside_repository(root)
    if packet_root.exists() or packet_root.is_symlink():
        raise release_evidence.ReleaseEvidenceError(
            "qualification packet initialization is create-only"
        )
    initialized_at = release_packet.timestamp(clock())
    plan = {
        "schema_version": "1.0",
        "evidence_class": "qualification-packet-plan",
        "status": "DRAFT",
        "candidate_commit": candidate,
        "initialized_at": initialized_at,
        "attempt_campaign_id": attempt_campaign_id,
        "paths": dict(PLAN_PATHS),
    }
    plan["plan_sha256"] = release_evidence.digest(plan)
    if errors := release_evidence.schema_errors(plan, "qualification_plan"):
        raise release_evidence.ReleaseEvidenceError(
            "invalid qualification packet plan: " + "; ".join(errors)
        )
    os.mkdir(root, 0o700)
    os.chmod(root, 0o700)
    for name in PACKET_DIRECTORIES:
        path = root / name
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
    release_packet.write_private_new(root / PLAN_NAME, plan)
    return {
        "status": "initialized",
        "candidate_commit": candidate,
        "attempt_campaign_id": attempt_campaign_id,
        "plan_sha256": plan["plan_sha256"],
        "ready_to_freeze": False,
        "missing_inputs": list(INPUT_LABELS),
    }


def preflight_packet(
    packet_root: Path,
    *,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
    policy_preparer: Callable[..., dict[str, Any]] = release_packet.prepare_trust_policy,
) -> dict[str, Any]:
    root = _existing_packet_root(packet_root)
    errors: list[str] = []
    missing_inputs: list[str] = []
    try:
        _scan_packet(root)
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
    policy_output = declared["trust_policy"]
    if policy_output.exists() or policy_output.is_symlink():
        errors.append("configured trust-policy output already exists")
    bindings: dict[str, Any] | None = None
    if not errors and not missing_inputs and current_candidate is not None:
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
                "target_config_sha256": policy["target_config_sha256"],
                "holdout_seal_sha256": policy["holdout_seal_sha256"],
                "privacy_host_identity_sha256": policy[
                    "privacy_host_identity_sha256"
                ],
                "pilot_protocol_sha256": policy["pilot_protocol_sha256"],
                "authority_count": len(policy["authorities"]),
            }
    ready = not errors and not missing_inputs and bindings is not None
    requirements = [
        {
            "input_id": input_id,
            "description": description,
            "path": plan["paths"][input_id],
            "status": "MISSING" if input_id in missing_inputs else "PRESENT",
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
        "errors": errors,
        "validated_bindings": bindings,
    }
    result["preflight_sha256"] = release_evidence.digest(result)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--packet-root", type=Path, required=True)
    initialize.add_argument("--attempt-campaign-id", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--packet-root", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            result = initialize_packet(args.packet_root, args.attempt_campaign_id)
        else:
            result = preflight_packet(args.packet_root)
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
