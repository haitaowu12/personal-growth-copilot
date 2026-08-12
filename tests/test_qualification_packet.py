from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import qualification_packet  # noqa: E402
import release_evidence  # noqa: E402
import release_packet  # noqa: E402


CANDIDATE = "a" * 40
FIXED_TIME = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class QualificationPacketTests(unittest.TestCase):
    def initialize(self, parent: Path) -> Path:
        root = parent / "private-qualification"
        qualification_packet.initialize_packet(
            root,
            "campaign-private-qualification-0001",
            source_identity=lambda _: CANDIDATE,
            clock=lambda: FIXED_TIME,
        )
        return root

    def populate_declared_inputs(self, root: Path) -> None:
        plan = json.loads((root / qualification_packet.PLAN_NAME).read_text())
        for input_id in qualification_packet.INPUT_LABELS:
            path = root / plan["paths"][input_id]
            path.write_bytes(release_evidence.canonical_bytes({"input": input_id}))
            os.chmod(path, 0o600)

    def test_init_is_private_create_only_and_contains_no_fake_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for name in qualification_packet.PACKET_DIRECTORIES:
                self.assertEqual(stat.S_IMODE((root / name).stat().st_mode), 0o700)
            files = [
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            ]
            self.assertEqual(files, [qualification_packet.PLAN_NAME])
            plan_path = root / qualification_packet.PLAN_NAME
            self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
            plan_bytes = plan_path.read_bytes()
            plan = json.loads(plan_bytes)
            self.assertEqual(plan_bytes, release_evidence.canonical_bytes(plan))
            self.assertEqual(release_evidence.schema_errors(plan, "qualification_plan"), [])
            self.assertEqual(
                plan["plan_sha256"],
                release_evidence.object_hash(plan, "plan_sha256"),
            )
            self.assertNotIn(b"PRIVATE KEY", plan_bytes)

            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError, "create-only"
            ):
                qualification_packet.initialize_packet(
                    root,
                    "campaign-private-qualification-0001",
                    source_identity=lambda _: CANDIDATE,
                )

    def test_preflight_reports_real_missing_inputs_without_calling_builder(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))

            def unexpected(**_: object) -> dict:
                self.fail("policy builder must not run with missing inputs")

            result = qualification_packet.preflight_packet(
                root,
                source_identity=lambda _: CANDIDATE,
                clock=lambda: FIXED_TIME,
                policy_preparer=unexpected,
            )
            self.assertEqual(result["status"], "NOT_READY")
            self.assertFalse(result["ready_to_freeze"])
            self.assertEqual(result["missing_inputs"], list(qualification_packet.INPUT_LABELS))
            self.assertEqual(result["errors"], [])
            self.assertIsNone(result["validated_bindings"])
            self.assertEqual(
                result["preflight_sha256"],
                release_evidence.object_hash(result, "preflight_sha256"),
            )

    def test_preflight_reuses_policy_validation_and_exposes_only_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            self.populate_declared_inputs(root)
            captured: dict[str, object] = {}

            def prepare(**kwargs: object) -> dict:
                captured.update(kwargs)
                return {
                    "qualification_plan_sha256": "0" * 64,
                    "target_config_sha256": "1" * 64,
                    "holdout_seal_sha256": "2" * 64,
                    "privacy_host_identity_sha256": "3" * 64,
                    "pilot_protocol_sha256": "4" * 64,
                    "authorities": [{} for _ in range(9)],
                }

            result = qualification_packet.preflight_packet(
                root,
                source_identity=lambda _: CANDIDATE,
                clock=lambda: FIXED_TIME,
                policy_preparer=prepare,
            )
            self.assertEqual(result["status"], "READY_TO_FREEZE")
            self.assertTrue(result["ready_to_freeze"])
            self.assertEqual(result["missing_inputs"], [])
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["validated_bindings"]["authority_count"], 9)
            self.assertEqual(
                result["validated_bindings"]["qualification_plan_sha256"],
                "0" * 64,
            )
            self.assertEqual(captured["candidate"], CANDIDATE)
            self.assertEqual(captured["packet_root"], root.resolve())
            self.assertNotIn("policy_sha256", result["validated_bindings"])

    def test_preflight_rejects_candidate_drift_private_keys_and_existing_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            private_key = root / "authorities" / "release.private.pem"
            private_key.write_text(
                "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"
            )
            os.chmod(private_key, 0o600)
            (root / "trust-policy.json").write_text("{}")
            os.chmod(root / "trust-policy.json", 0o600)
            result = qualification_packet.preflight_packet(
                root,
                source_identity=lambda _: "b" * 40,
                clock=lambda: FIXED_TIME,
            )
            self.assertFalse(result["ready_to_freeze"])
            self.assertIn(
                "qualification packet contains PEM private-key material",
                result["errors"],
            )
            self.assertIn(
                "qualification plan differs from the exact clean candidate checkout",
                result["errors"],
            )
            self.assertIn("configured trust-policy output already exists", result["errors"])

    def test_preflight_rejects_group_readable_packet_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            path = root / "target" / "target-config.json"
            path.write_text("{}")
            os.chmod(path, 0o640)
            result = qualification_packet.preflight_packet(
                root,
                source_identity=lambda _: CANDIDATE,
                clock=lambda: FIXED_TIME,
            )
            self.assertFalse(result["ready_to_freeze"])
            self.assertIn(
                "qualification packet files must use mode 0600",
                result["errors"],
            )

    def test_policy_freeze_itself_rejects_private_key_material_and_broad_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            private_key = root / "authorities" / "release.private.pem"
            private_key.write_text(
                "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"
            )
            os.chmod(private_key, 0o600)
            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError, "private-key material"
            ):
                release_packet.prepare_trust_policy(
                    packet_root=root,
                    config_path=root / "target" / "target-config.json",
                    holdout_seal_path=root / "holdout" / "holdout-seal.json",
                    privacy_host_identity_path=root / "privacy" / "host-identity.json",
                    pilot_protocol_path=root / "pilot" / "protocol.json",
                    authorities_path=root / "authorities" / "authority-roster.json",
                    attempt_campaign_id="campaign-private-qualification-0001",
                    candidate=CANDIDATE,
                    frozen=FIXED_TIME,
                )
            private_key.unlink()
            os.chmod(root, 0o755)
            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError, "directories must use mode 0700"
            ):
                release_packet.prepare_trust_policy(
                    packet_root=root,
                    config_path=root / "target" / "target-config.json",
                    holdout_seal_path=root / "holdout" / "holdout-seal.json",
                    privacy_host_identity_path=root / "privacy" / "host-identity.json",
                    pilot_protocol_path=root / "pilot" / "protocol.json",
                    authorities_path=root / "authorities" / "authority-roster.json",
                    attempt_campaign_id="campaign-private-qualification-0001",
                    candidate=CANDIDATE,
                    frozen=FIXED_TIME,
                )
            os.chmod(root, 0o700)

    def test_preflight_rejects_unreadable_subtree_instead_of_skipping_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            opaque = root / "review" / "opaque"
            opaque.mkdir(mode=0o700)
            hidden = opaque / "signing-key.pem"
            hidden.write_text(
                "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"
            )
            os.chmod(hidden, 0o600)
            os.chmod(opaque, 0o000)
            try:
                result = qualification_packet.preflight_packet(
                    root,
                    source_identity=lambda _: CANDIDATE,
                    clock=lambda: FIXED_TIME,
                )
                self.assertFalse(result["ready_to_freeze"])
                self.assertIn(
                    "qualification packet directories must use mode 0700",
                    result["errors"],
                )
            finally:
                os.chmod(opaque, 0o700)

    def test_plan_policy_destination_is_fixed_to_the_builder_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = self.initialize(Path(directory_name))
            plan_path = root / qualification_packet.PLAN_NAME
            plan = json.loads(plan_path.read_text())
            plan["paths"]["trust_policy"] = "review/configured.json"
            plan["plan_sha256"] = release_evidence.object_hash(plan, "plan_sha256")
            plan_path.write_bytes(release_evidence.canonical_bytes(plan))
            os.chmod(plan_path, 0o600)
            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError,
                "invalid qualification packet plan",
            ):
                qualification_packet.preflight_packet(
                    root,
                    source_identity=lambda _: CANDIDATE,
                    clock=lambda: FIXED_TIME,
                )

    def test_policy_preparation_rejects_preregistration_inputs_outside_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name)
            root = self.initialize(parent)
            outside = parent / "outside.json"
            outside.write_text("{}")
            os.chmod(outside, 0o600)
            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError, "packet directory"
            ):
                release_packet.prepare_trust_policy(
                    packet_root=root,
                    config_path=outside,
                    holdout_seal_path=outside,
                    privacy_host_identity_path=outside,
                    pilot_protocol_path=outside,
                    authorities_path=outside,
                    attempt_campaign_id="campaign-private-qualification-0001",
                    candidate=CANDIDATE,
                    frozen=FIXED_TIME,
                )


if __name__ == "__main__":
    unittest.main()
