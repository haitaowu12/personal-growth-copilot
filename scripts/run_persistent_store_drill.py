#!/usr/bin/env python3
"""Exercise persistent record lifecycle controls on one named private host root.

The receipt is suitable as one input to the privacy-preflight source pack.  It
does not sign itself, authorize production persistence, prove encryption or
backup behavior, or replace the independent privacy-audit witness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = (
    ROOT
    / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS))

import persistent_record_store  # noqa: E402
import record_store  # noqa: E402

SCHEMA = ROOT / "release/persistent-store-drill.schema.json"
ADAPTER = SKILL_SCRIPTS / "persistent_record_store.py"


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
        raise ValueError("drill clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def source_identity() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError("persistent-store drill requires a clean source tree")
    return commit


class DrillClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class DrillAuthorizationVerifier:
    def __init__(self, authorization_id: str, root: Path) -> None:
        self.authorization_id = authorization_id
        self.root = root

    def verify(self, authorization, storage_root: Path) -> bool:
        return (
            authorization.authorization_id == self.authorization_id
            and storage_root == self.root
        )


class DrillConsentVerifier:
    def __init__(self, clock: DrillClock) -> None:
        self.clock = clock
        self.allowed: set[tuple[str, str, str]] = set()

    def confirmation(self, preview, label: str):
        opaque = "att_" + hashlib.sha256(
            f"drill:{label}:{preview.preview_id}".encode()
        ).hexdigest()[:32]
        observed = timestamp(self.clock())
        self.allowed.add((opaque, preview.preview_id, observed))
        return record_store.HostUserConfirmation(opaque, preview.preview_id, observed)

    def verify(self, confirmation, preview) -> bool:
        key = (
            confirmation.attestation_id,
            confirmation.preview_id,
            confirmation.confirmed_at,
        )
        if key not in self.allowed or confirmation.preview_id != preview.preview_id:
            return False
        self.allowed.remove(key)
        return True


def schema_errors(value: object) -> list[str]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def run_drill(
    *,
    storage_root: Path,
    record_path: Path,
    named_host: str,
    environment_id: str,
    candidate_commit: str,
    clock: DrillClock,
    audit_retention_days: int = 1,
) -> dict:
    storage_root = storage_root.resolve(strict=True)
    if any((storage_root / name).exists() for name in (
        persistent_record_store.STATE_NAME,
        persistent_record_store.LOCK_NAME,
    )):
        raise ValueError("drill storage root must not contain an existing record store")
    record_bytes = record_path.read_bytes()
    record = json.loads(record_bytes.decode("utf-8"))
    authorization_id = "pauth_" + secrets.token_hex(16)
    authorization = persistent_record_store.HostPersistenceAuthorization(
        authorization_id=authorization_id,
        named_host=named_host,
        environment_id=environment_id,
        storage_root_sha256=persistent_record_store.storage_root_identity(storage_root),
        issued_at=timestamp(clock() - timedelta(minutes=1)),
        expires_at=timestamp(clock() + timedelta(days=7)),
    )
    verifier = DrillAuthorizationVerifier(authorization_id, storage_root)
    consent = DrillConsentVerifier(clock)
    checks: list[dict[str, str]] = []
    state_hash: str | None = None

    rejected = DrillAuthorizationVerifier("pauth_" + "0" * 32, storage_root)
    try:
        persistent_record_store.PersistentRecordStore(
            storage_root=storage_root,
            authorization=authorization,
            authorization_verifier=rejected,
            consent_verifier=consent,
            clock=clock,
            audit_retention_days=audit_retention_days,
        )
        raise AssertionError("forged persistence authorization was accepted")
    except persistent_record_store.PersistentStoreError:
        checks.append(
            {
                "check_id": "authorization_gate",
                "status": "PASS",
                "detail": "An unverified authorization was rejected before state creation.",
            }
        )

    def open_store():
        return persistent_record_store.PersistentRecordStore(
            storage_root=storage_root,
            authorization=authorization,
            authorization_verifier=verifier,
            consent_verifier=consent,
            clock=clock,
            audit_retention_days=audit_retention_days,
        )

    store = open_store()
    preview = store.preview_upsert(record, "Host lifecycle drill create")
    token = store.issue_consent(
        preview.preview_id, consent.confirmation(preview, "create")
    )
    created = store.commit(preview.preview_id, token.token_id)
    restarted = open_store()
    if restarted.read(record["record_id"]).revision_id != created.revision_id:
        raise AssertionError("committed record did not survive restart")
    checks.append(
        {
            "check_id": "create_restart",
            "status": "PASS",
            "detail": "A consented create survived a fresh adapter instance.",
        }
    )

    exported = restarted.export(record["record_id"])
    if exported.content_sha256 != digest(record):
        raise AssertionError("export content hash differs from the committed record")
    checks.append(
        {
            "check_id": "export_integrity",
            "status": "PASS",
            "detail": "Export returned the exact committed record hash after restart.",
        }
    )

    clock.advance(minutes=1)
    correction = restarted.preview_correction(
        record["record_id"],
        correction_id="correction-host-drill",
        target_id="pref-1",
        replacement_or_action="Supersede the invented drill preference.",
        purpose="Host lifecycle drill correction",
    )
    correction_token = restarted.issue_consent(
        correction.preview_id, consent.confirmation(correction, "correction")
    )
    restarted.commit(correction.preview_id, correction_token.token_id)
    corrected = open_store()
    if not corrected.read(record["record_id"]).record["preferences"][0][
        "superseded"
    ]:
        raise AssertionError("correction did not survive restart")
    checks.append(
        {
            "check_id": "correction_restart",
            "status": "PASS",
            "detail": "A consented correction superseded its target and survived restart.",
        }
    )

    clock.advance(minutes=1)
    deletion = corrected.preview_delete(
        record["record_id"], "Host lifecycle drill deletion"
    )
    deletion_token = corrected.issue_consent(
        deletion.preview_id, consent.confirmation(deletion, "delete")
    )
    result = corrected.delete(deletion.preview_id, deletion_token.token_id)
    deleted = open_store()
    try:
        deleted.read(record["record_id"])
        raise AssertionError("deleted record remained readable after restart")
    except record_store.RecordNotFound:
        pass
    state_bytes = deleted.state_path.read_bytes()
    state_hash = hashlib.sha256(state_bytes).hexdigest()
    sensitive_markers = [record.get("purpose", ""), "alice@example.com"]
    if result.content_present_after or any(
        marker and marker.encode("utf-8") in state_bytes for marker in sensitive_markers
    ):
        raise AssertionError("content remained in the logical state after deletion")
    checks.append(
        {
            "check_id": "deletion_restart",
            "status": "PASS",
            "detail": "Deletion removed current, revision, preview, token, and attestation content across restart.",
        }
    )

    clock.advance(days=audit_retention_days + 1)
    removed = deleted.enforce_retention()
    if removed < 1 or deleted.audit_events:
        raise AssertionError("bounded audit retention did not purge expired metadata")
    checks.append(
        {
            "check_id": "bounded_audit_retention",
            "status": "PASS",
            "detail": "Expired content-free audit metadata was removed under the configured retention period.",
        }
    )

    deleted.state_path.unlink(missing_ok=True)
    (storage_root / persistent_record_store.LOCK_NAME).unlink(missing_ok=True)
    leftovers = [item.name for item in storage_root.iterdir()]
    if leftovers:
        raise AssertionError("drill cleanup left files in the dedicated storage root")
    checks.append(
        {
            "check_id": "drill_cleanup",
            "status": "PASS",
            "detail": "The dedicated drill root was returned to an empty state.",
        }
    )

    report = {
        "schema_version": "1.0",
        "evidence_class": "persistent-store-host-drill",
        "qualification_claim_allowed": False,
        "status": "PASS",
        "candidate_commit": candidate_commit,
        "generated_at": timestamp(clock()),
        "named_host": named_host,
        "environment_id": environment_id,
        "storage_root_sha256": persistent_record_store.storage_root_identity(
            storage_root
        ),
        "adapter_sha256": file_hash(ADAPTER),
        "record_fixture_sha256": hashlib.sha256(record_bytes).hexdigest(),
        "audit_retention_days": audit_retention_days,
        "checks": checks,
        "post_deletion_state_sha256": state_hash,
        "claim_limit": (
            "This host-local drill verifies adapter authorization, atomic logical "
            "persistence, restart, correction, export, deletion, and bounded audit "
            "retention for invented data. It does not prove encryption, backup erasure, "
            "no-sync placement, incident response, participant consent, or production readiness."
        ),
    }
    report["report_sha256"] = digest(report)
    if errors := schema_errors(report):
        raise ValueError("persistent drill report schema failure: " + "; ".join(errors))
    return report


def write_private_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((json.dumps(value, indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument(
        "--record", type=Path, default=ROOT / "examples/growth-record.example.json"
    )
    parser.add_argument("--named-host", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--audit-retention-days", type=int, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_drill(
            storage_root=args.storage_root,
            record_path=args.record,
            named_host=args.named_host,
            environment_id=args.environment_id,
            candidate_commit=source_identity(),
            clock=DrillClock(datetime.now(timezone.utc)),
            audit_retention_days=args.audit_retention_days,
        )
        write_private_new(args.output, report)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "report_sha256": report["report_sha256"],
                },
                indent=2,
            )
        )
        return 0
    except (
        AssertionError,
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
        record_store.RecordStoreError,
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
