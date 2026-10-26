from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import persistent_record_store  # noqa: E402
import record_store  # noqa: E402


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


class FakeAuthorizationVerifier:
    def __init__(self, authorization_id: str, root: Path) -> None:
        self.authorization_id = authorization_id
        self.root = root.resolve()

    def verify(self, authorization, storage_root: Path) -> bool:
        return (
            authorization.authorization_id == self.authorization_id
            and storage_root == self.root
        )


class FakeConsentVerifier:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.allowed: set[tuple[str, str, str]] = set()

    def confirmation(self, preview, label: str):
        attestation_id = "att_" + hashlib.sha256(
            f"{label}:{preview.preview_id}".encode()
        ).hexdigest()[:32]
        confirmed_at = self.clock.current.isoformat().replace("+00:00", "Z")
        self.allowed.add((attestation_id, preview.preview_id, confirmed_at))
        return record_store.HostUserConfirmation(
            attestation_id, preview.preview_id, confirmed_at
        )

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


class PersistentRecordStoreTests(unittest.TestCase):
    def test_unsupported_locking_host_fails_instead_of_using_unlocked_storage(self):
        with tempfile.TemporaryDirectory() as directory_name, mock.patch.object(
            persistent_record_store, "fcntl", None
        ):
            with self.assertRaisesRegex(
                persistent_record_store.PersistentStoreError,
                "POSIX file-locking host",
            ):
                persistent_record_store.AtomicPersistentRecordStore(
                    Path(directory_name),
                    authorization=self.authorization(Path(directory_name)),
                    authorization_verifier=lambda *_: True,
                )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.clock = FakeClock()
        self.consent = FakeConsentVerifier(self.clock)
        self.authorization = persistent_record_store.HostPersistenceAuthorization(
            authorization_id="pauth_" + "1" * 32,
            named_host="test-host",
            environment_id="test-host-0001",
            storage_root_sha256=persistent_record_store.storage_root_identity(
                self.root
            ),
            issued_at=(NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            expires_at=(NOW + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        )
        self.auth = FakeAuthorizationVerifier(
            self.authorization.authorization_id, self.root
        )
        self.record = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )

    def open(self, **kwargs):
        return persistent_record_store.PersistentRecordStore(
            storage_root=self.root,
            authorization=self.authorization,
            authorization_verifier=self.auth,
            consent_verifier=self.consent,
            clock=self.clock,
            **kwargs,
        )

    def issue(self, store, preview, label: str):
        confirmation = self.consent.confirmation(preview, label)
        return store.issue_consent(preview.preview_id, confirmation)

    def commit_initial(self, store):
        preview = store.preview_upsert(self.record, "Create approved record")
        token = self.issue(store, preview, "create")
        return store.commit(preview.preview_id, token.token_id)

    def test_restart_correction_export_and_complete_logical_deletion(self):
        first = self.open()
        created = self.commit_initial(first)
        self.assertTrue(first.state_path.is_file())
        self.assertEqual(stat_mode(first.state_path), 0o600)

        restarted = self.open()
        self.assertEqual(
            restarted.read(self.record["record_id"]).revision_id,
            created.revision_id,
        )
        exported = restarted.export(self.record["record_id"])
        self.assertEqual(
            exported.content_sha256,
            hashlib.sha256(
                json.dumps(
                    self.record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
        )

        self.clock.advance(minutes=1)
        correction = restarted.preview_correction(
            self.record["record_id"],
            correction_id="correction-persistent-1",
            target_id="pref-1",
            replacement_or_action="This preference is no longer accurate.",
            purpose="Apply a user correction",
        )
        correction_token = self.issue(restarted, correction, "correction")
        restarted.commit(correction.preview_id, correction_token.token_id)

        corrected = self.open()
        self.assertTrue(
            corrected.read(self.record["record_id"])
            .record["preferences"][0]["superseded"]
        )
        self.clock.advance(minutes=1)
        deletion = corrected.preview_delete(
            self.record["record_id"], "User requested complete deletion"
        )
        deletion_token = self.issue(corrected, deletion, "delete")
        result = corrected.delete(deletion.preview_id, deletion_token.token_id)
        self.assertFalse(result.content_present_after)

        final = self.open()
        with self.assertRaises(record_store.RecordNotFound):
            final.read(self.record["record_id"])
        self.assertEqual(
            final.content_inventory(self.record["record_id"]),
            {"current": 0, "revisions": 0, "pending_previews": 0},
        )
        state_text = final.state_path.read_text(encoding="utf-8")
        self.assertNotIn(self.record["purpose"], state_text)
        self.assertNotIn("alice@example.com", state_text)

    def test_authorization_is_exact_time_bounded_and_host_verified(self):
        mismatched = copy.deepcopy(self.authorization)
        mismatched = persistent_record_store.HostPersistenceAuthorization(
            **{
                **mismatched.__dict__,
                "storage_root_sha256": "0" * 64,
            }
        )
        with self.assertRaisesRegex(
            persistent_record_store.PersistentStoreError, "another storage root"
        ):
            persistent_record_store.PersistentRecordStore(
                storage_root=self.root,
                authorization=mismatched,
                authorization_verifier=self.auth,
                consent_verifier=self.consent,
                clock=self.clock,
            )

        rejected = FakeAuthorizationVerifier("pauth_" + "f" * 32, self.root)
        with self.assertRaisesRegex(
            persistent_record_store.PersistentStoreError, "not verified"
        ):
            persistent_record_store.PersistentRecordStore(
                storage_root=self.root,
                authorization=self.authorization,
                authorization_verifier=rejected,
                consent_verifier=self.consent,
                clock=self.clock,
            )

        store = self.open()
        self.clock.advance(days=31)
        with self.assertRaisesRegex(
            persistent_record_store.PersistentStoreError, "not currently valid"
        ):
            store.content_inventory(self.record["record_id"])

    def test_state_tampering_and_nonprivate_roots_fail_closed(self):
        store = self.open()
        self.commit_initial(store)
        state = json.loads(store.state_path.read_text(encoding="utf-8"))
        state["current"][self.record["record_id"]]["record"]["purpose"] = "tampered"
        store.state_path.write_text(
            json.dumps(state, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(store.state_path, 0o600)
        with self.assertRaisesRegex(
            persistent_record_store.PersistentStoreError, "self-hash mismatch"
        ):
            self.open()

        other = Path(self.temporary.name) / "nonprivate"
        other.mkdir(mode=0o755)
        bad_authorization = persistent_record_store.HostPersistenceAuthorization(
            authorization_id="pauth_" + "2" * 32,
            named_host="test-host",
            environment_id="test-host-0002",
            storage_root_sha256=persistent_record_store.storage_root_identity(other),
            issued_at=(NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            expires_at=(NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        )
        with self.assertRaisesRegex(
            persistent_record_store.PersistentStoreError, "mode 0700"
        ):
            persistent_record_store.PersistentRecordStore(
                storage_root=other,
                authorization=bad_authorization,
                authorization_verifier=FakeAuthorizationVerifier(
                    bad_authorization.authorization_id, other
                ),
                consent_verifier=self.consent,
                clock=self.clock,
            )

    def test_failed_atomic_write_rolls_back_memory_and_disk(self):
        store = self.open()
        before = store.content_inventory(self.record["record_id"])
        with mock.patch.object(
            store, "_atomic_write_unlocked", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                store.preview_upsert(self.record, "Create")
        self.assertFalse(store.state_path.exists())
        self.assertEqual(store.content_inventory(self.record["record_id"]), before)

    def test_cross_instance_stale_write_is_rejected(self):
        creator = self.open()
        self.commit_initial(creator)
        one = self.open()
        two = self.open()

        first_record = copy.deepcopy(self.record)
        first_record["purpose"] = "First persistent update"
        first_record["updated_at"] = "2026-09-11T12:01:00Z"
        second_record = copy.deepcopy(self.record)
        second_record["purpose"] = "Second persistent update"
        second_record["updated_at"] = "2026-09-11T12:02:00Z"
        first = one.preview_upsert(first_record, "First")
        second = two.preview_upsert(second_record, "Second")
        first_token = self.issue(one, first, "first")
        second_token = self.issue(two, second, "second")
        one.commit(first.preview_id, first_token.token_id)
        with self.assertRaises(
            (record_store.ConsentError, record_store.RevisionConflict)
        ):
            two.commit(second.preview_id, second_token.token_id)
        self.assertEqual(
            self.open().read(self.record["record_id"]).record["purpose"],
            "First persistent update",
        )

    def test_bounded_audit_retention_is_enforced(self):
        store = self.open(audit_retention_days=1)
        self.commit_initial(store)
        self.assertEqual(len(store.audit_events), 1)
        self.clock.advance(days=2)
        removed = store.enforce_retention()
        self.assertEqual(removed, 1)
        self.assertEqual(store.audit_events, ())
        reopened = self.open(audit_retention_days=1)
        self.assertEqual(reopened.audit_events, ())


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
