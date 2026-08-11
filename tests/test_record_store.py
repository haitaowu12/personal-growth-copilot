from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skill/personal-growth-copilot/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import record_store  # noqa: E402

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, current: datetime):
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


class FakeHostConsentVerifier:
    """Test-only host boundary; unregistered/model-created strings fail."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.allowed: set[tuple[str, str, str]] = set()

    def confirmation(
        self, preview: record_store.ChangePreview, attestation_id: str
    ) -> record_store.HostUserConfirmation:
        opaque_id = "att_" + hashlib.sha256(
            f"{attestation_id}:{preview.preview_id}".encode("utf-8")
        ).hexdigest()[:32]
        confirmed_at = self.clock.current.isoformat().replace("+00:00", "Z")
        self.allowed.add((opaque_id, preview.preview_id, confirmed_at))
        return record_store.HostUserConfirmation(
            attestation_id=opaque_id,
            preview_id=preview.preview_id,
            confirmed_at=confirmed_at,
        )

    def verify(
        self,
        confirmation: record_store.HostUserConfirmation,
        preview: record_store.ChangePreview,
    ) -> bool:
        key = (
            confirmation.attestation_id,
            preview.preview_id,
            confirmation.confirmed_at,
        )
        if key not in self.allowed:
            return False
        self.allowed.remove(key)
        return True


class StatelessHostConsentVerifier:
    """Signature-like verifier used to prove the store prevents replay itself."""

    @staticmethod
    def confirmation(
        preview: record_store.ChangePreview, confirmed_at: str
    ) -> record_store.HostUserConfirmation:
        attestation_id = "att_" + hashlib.sha256(
            f"trusted-host:{preview.preview_id}:{confirmed_at}".encode("utf-8")
        ).hexdigest()[:32]
        return record_store.HostUserConfirmation(
            attestation_id, preview.preview_id, confirmed_at
        )

    def verify(
        self,
        confirmation: record_store.HostUserConfirmation,
        preview: record_store.ChangePreview,
    ) -> bool:
        expected = self.confirmation(preview, confirmation.confirmed_at)
        return confirmation == expected


class RecordStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(NOW)
        self.verifier = FakeHostConsentVerifier(self.clock)
        self.store = record_store.InMemoryRecordStore(
            consent_verifier=self.verifier,
            clock=self.clock,
        )
        self.record = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )

    def issue(
        self,
        preview: record_store.ChangePreview,
        attestation_id: str,
        *,
        ttl_seconds: int = 300,
    ) -> record_store.ConsentToken:
        confirmation = self.verifier.confirmation(preview, attestation_id)
        return self.store.issue_consent(
            preview.preview_id, confirmation, ttl_seconds=ttl_seconds
        )

    def commit_record(self, record: dict | None = None):
        preview = self.store.preview_upsert(
            record or self.record, "Create user-approved record"
        )
        token = self.issue(preview, "host-attestation-create")
        return self.store.commit(preview.preview_id, token.token_id)

    def test_verified_attestation_atomic_commit_revision_and_minimized_audit(self) -> None:
        preview = self.store.preview_upsert(
            self.record, "Create user-approved record"
        )
        preview.delta[0].after["purpose"] = "tampered caller copy"
        self.assertEqual(
            self.store.get_preview(preview.preview_id).delta[0].after["purpose"],
            self.record["purpose"],
        )
        forged = record_store.HostUserConfirmation(
            "att_ffffffffffffffffffffffffffffffff",
            preview.preview_id,
            self.clock.current.isoformat().replace("+00:00", "Z"),
        )
        with self.assertRaises(record_store.ConsentError):
            self.store.issue_consent(preview.preview_id, forged)
        malformed = record_store.HostUserConfirmation(
            "att_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            preview.preview_id,
            "not-a-time",
        )
        with self.assertRaises(record_store.ConsentError):
            self.store.issue_consent(preview.preview_id, malformed)
        with self.assertRaises(record_store.ConsentError):
            self.store.commit(preview.preview_id, "not-a-token")

        token = self.issue(preview, "host-attestation-create")
        result = self.store.commit(preview.preview_id, token.token_id)
        self.assertEqual(result.status, "committed")
        self.assertEqual(self.store.read(self.record["record_id"]).record, self.record)
        self.assertEqual(
            self.store.read(self.record["record_id"], result.revision_id).record,
            self.record,
        )

        audit = self.store.audit_events[-1]
        self.assertEqual(audit.consent_token_id, token.token_id)
        self.assertNotIn(self.record["purpose"], repr(audit))
        self.assertNotEqual(audit.revision_after, "rev-" + record_store._digest(self.record))
        self.assertEqual(
            self.store.retention_inventory(self.record["record_id"]),
            {
                "current": 1,
                "revisions": 1,
                "pending_previews": 0,
                "tokens": 0,
                "attestations": 0,
                "audit_events": 1,
            },
        )
        with self.assertRaises(record_store.ConsentError):
            self.store.commit(preview.preview_id, token.token_id)

    def test_invalid_or_off_record_never_changes_state(self) -> None:
        invalid = copy.deepcopy(self.record)
        invalid["preferences"][0]["raw_transcript"] = "must not persist"
        with self.assertRaises(record_store.InvalidRecord):
            self.store.preview_upsert(invalid, "Invalid")
        with self.assertRaises(record_store.RecordNotFound):
            self.store.read(self.record["record_id"])

        off = copy.deepcopy(self.record)
        off["memory_policy"] = "OFF"
        with self.assertRaises(record_store.ConsentError):
            self.store.preview_upsert(off, "Policy is off")

        identifying = copy.deepcopy(self.record)
        identifying["record_id"] = "alice@example.com"
        with self.assertRaises(record_store.InvalidRecord):
            self.store.preview_upsert(identifying, "Identifier must be opaque")

    def test_token_is_preview_bound_single_use_revocable_and_exact_expiry(self) -> None:
        first = self.store.preview_upsert(self.record, "First")
        second_record = copy.deepcopy(self.record)
        second_record["purpose"] = "Different candidate"
        second = self.store.preview_upsert(second_record, "Second")
        token = self.issue(first, "host-attestation-first")
        with self.assertRaises(record_store.ConsentError):
            self.store.commit(second.preview_id, token.token_id)
        with self.assertRaises(record_store.ConsentError):
            self.issue(first, "host-attestation-duplicate")
        self.assertEqual(self.store.revoke_consent(token.token_id).status, "revoked")
        with self.assertRaises(record_store.ConsentError):
            self.store.commit(first.preview_id, token.token_id)
        with self.assertRaises(record_store.ConsentError):
            self.issue(first, "host-attestation-after-revoke")

        short = self.issue(second, "host-attestation-short", ttl_seconds=1)
        self.clock.advance(seconds=1)
        with self.assertRaises(record_store.ConsentError):
            self.store.commit(second.preview_id, short.token_id)

    def test_store_owned_clock_fails_closed_on_rollback(self) -> None:
        preview = self.store.preview_upsert(self.record, "Create")
        token = self.issue(preview, "host-attestation-clock")
        self.clock.current -= timedelta(seconds=1)
        with self.assertRaisesRegex(record_store.RecordStoreError, "clock moved backward"):
            self.store.commit(preview.preview_id, token.token_id)
        self.assertEqual(
            self.store.content_inventory(self.record["record_id"]),
            {"current": 0, "revisions": 0, "pending_previews": 1},
        )

    def test_expired_token_does_not_make_host_attestation_replayable(self) -> None:
        clock = FakeClock(NOW)
        verifier = StatelessHostConsentVerifier()
        store = record_store.InMemoryRecordStore(
            consent_verifier=verifier,
            clock=clock,
        )
        preview = store.preview_upsert(
            self.record, "Create", preview_ttl_seconds=10
        )
        confirmed_at = clock.current.isoformat().replace("+00:00", "Z")
        confirmation = verifier.confirmation(preview, confirmed_at)
        token = store.issue_consent(
            preview.preview_id, confirmation, ttl_seconds=1
        )
        clock.advance(seconds=1)
        with self.assertRaises(record_store.ConsentError):
            store.commit(preview.preview_id, token.token_id)
        with self.assertRaisesRegex(record_store.ConsentError, "already used"):
            store.issue_consent(preview.preview_id, confirmation, ttl_seconds=1)

    def test_concurrent_stale_writes_allow_exactly_one_commit(self) -> None:
        self.commit_record()
        first = copy.deepcopy(self.record)
        first["purpose"] = "First concurrent update"
        first["updated_at"] = "2026-08-12T12:01:00Z"
        second = copy.deepcopy(self.record)
        second["purpose"] = "Second concurrent update"
        second["updated_at"] = "2026-08-12T12:02:00Z"
        first_preview = self.store.preview_upsert(first, "First update")
        second_preview = self.store.preview_upsert(second, "Second update")
        first_token = self.issue(first_preview, "host-attestation-first-update")
        second_token = self.issue(second_preview, "host-attestation-second-update")
        barrier = threading.Barrier(3)
        successes: list[record_store.CommitResult] = []
        failures: list[Exception] = []

        def run(preview_id: str, token_id: str) -> None:
            barrier.wait()
            try:
                successes.append(self.store.commit(preview_id, token_id))
            except Exception as error:  # capture the rejected competing writer
                failures.append(error)

        threads = [
            threading.Thread(
                target=run, args=(first_preview.preview_id, first_token.token_id)
            ),
            threading.Thread(
                target=run, args=(second_preview.preview_id, second_token.token_id)
            ),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(
            failures[0], (record_store.ConsentError, record_store.RevisionConflict)
        )
        self.assertEqual(
            self.store.read(self.record["record_id"]).revision_id,
            successes[0].revision_id,
        )

    def test_audit_failure_cannot_partially_commit(self) -> None:
        preview = self.store.preview_upsert(self.record, "Create")
        token = self.issue(preview, "host-attestation-fault")
        with patch.object(
            self.store, "_make_audit", side_effect=RuntimeError("injected audit failure")
        ):
            with self.assertRaises(RuntimeError):
                self.store.commit(preview.preview_id, token.token_id)
        self.assertEqual(
            self.store.content_inventory(self.record["record_id"]),
            {"current": 0, "revisions": 0, "pending_previews": 1},
        )
        self.assertEqual(self.store.audit_events, ())
        result = self.store.commit(preview.preview_id, token.token_id)
        self.assertEqual(result.status, "committed")

    def test_correction_supersedes_supported_targets_and_rejects_ambiguous_ones(self) -> None:
        created = self.commit_record()
        self.clock.advance(minutes=1)
        preview = self.store.preview_correction(
            self.record["record_id"],
            correction_id="correction-1",
            target_id="pref-1",
            replacement_or_action="Remove this preference; it is no longer accurate.",
            purpose="Apply the user's correction",
        )
        token = self.issue(preview, "host-attestation-correction")
        corrected = self.store.commit(preview.preview_id, token.token_id)
        current = self.store.read(self.record["record_id"])
        self.assertTrue(current.record["preferences"][0]["superseded"])
        self.assertEqual(current.record["corrections"][0]["target_id"], "pref-1")
        self.assertFalse(
            self.store.read(self.record["record_id"], created.revision_id)
            .record["preferences"][0]["superseded"]
        )
        self.assertNotEqual(created.revision_id, corrected.revision_id)

        self.clock.advance(minutes=1)
        with self.assertRaisesRegex(record_store.RecordStoreError, "goals"):
            self.store.preview_correction(
                self.record["record_id"],
                correction_id="correction-goal",
                target_id="goal-1",
                replacement_or_action="Remove this goal.",
                purpose="Apply a goal correction",
            )

    def test_export_is_copy_safe_and_delete_erases_every_internal_content_location(self) -> None:
        self.commit_record()
        exported = self.store.export(self.record["record_id"])
        exported.record["purpose"] = "caller mutation"
        self.assertEqual(
            self.store.read(self.record["record_id"]).record["purpose"],
            self.record["purpose"],
        )

        pending = copy.deepcopy(self.record)
        pending["purpose"] = "Pending stale content"
        pending["updated_at"] = "2026-08-12T12:03:00Z"
        pending_preview = self.store.preview_upsert(
            pending, "A pending update that deletion must purge"
        )
        preview = self.store.preview_delete(
            self.record["record_id"], "User requested complete deletion"
        )
        token = self.issue(preview, "host-attestation-delete")
        deleted = self.store.delete(preview.preview_id, token.token_id)
        self.assertTrue(deleted.content_revisions_deleted >= 1)
        self.assertTrue(deleted.pending_previews_deleted >= 2)
        self.assertFalse(deleted.record_present_after)
        self.assertFalse(deleted.content_present_after)
        self.assertGreaterEqual(deleted.retained_audit_events, 1)
        self.assertEqual(
            self.store.content_inventory(self.record["record_id"]),
            {"current": 0, "revisions": 0, "pending_previews": 0},
        )
        with self.assertRaises(record_store.RecordStoreError):
            self.store.get_preview(pending_preview.preview_id)
        self.assertEqual(
            self.store.retention_inventory(self.record["record_id"]),
            {
                "current": 0,
                "revisions": 0,
                "pending_previews": 0,
                "tokens": 0,
                "attestations": 0,
                "audit_events": deleted.retained_audit_events,
            },
        )
        self.assertNotIn("alice@example.com", repr(self.store.audit_events))
        with self.assertRaises(record_store.RecordNotFound):
            self.store.read(self.record["record_id"])
        with self.assertRaises(record_store.RecordNotFound):
            self.store.read(self.record["record_id"], exported.revision_id)


if __name__ == "__main__":
    unittest.main()
