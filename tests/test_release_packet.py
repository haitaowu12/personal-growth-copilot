from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import release_evidence  # noqa: E402
import release_packet  # noqa: E402
import test_release_evidence  # noqa: E402


class ReleasePacketTests(unittest.TestCase):
    def test_attempt_artifact_is_derived_from_exact_self_hashed_verification(self):
        candidate = "a" * 40
        verification = {
            "schema_version": "1.0",
            "evidence_class": "externally-witnessed-attempt-inventory",
            "qualification_claim_allowed": False,
            "verification_status": "pass",
            "inventory_status": "PASS",
            "qualification_ready": True,
            "candidate_commit": candidate,
            "campaign_id": "campaign-attempts-0001",
            "config_sha256": "1" * 64,
            "run_plan_sha256": "2" * 64,
            "result_manifest_sha256": "3" * 64,
            "witness_head_sha256": "4" * 64,
            "event_count": 100,
            "assertions": {
                "immutable_inventory": True,
                "all_attempts_accounted_for": True,
                "submitted_results_complete": True,
                "provider_access_enforced": True,
                "preregistered_run_plan_bound": True,
                "external_witness_receipts_verified": True,
                "all_artifacts_preserved": True,
                "omitted_attempt_count": 0,
                "attempt_count": 40,
                "submitted_result_count": 9,
            },
            "provider_access_control_sha256": "5" * 64,
            "artifact_inventory_sha256": "6" * 64,
            "hard_failures": [],
            "errors": [],
        }
        verification["inventory_sha256"] = release_evidence.digest(verification)
        artifact = release_packet.attempt_artifact(
            verification,
            candidate_commit=candidate,
            executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(artifact["gate"], "attempt_inventory")
        self.assertEqual(artifact["status"], "PASS")
        self.assertEqual(artifact["evidence_refs"][0], verification["inventory_sha256"])
        self.assertEqual(
            artifact["artifact_sha256"],
            release_evidence.object_hash(artifact, "artifact_sha256"),
        )
        tampered = dict(verification)
        tampered["event_count"] += 1
        with self.assertRaises(release_evidence.ReleaseEvidenceError):
            release_packet.attempt_artifact(
                tampered,
                candidate_commit=candidate,
                executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_canonical_signed_receipt_advances_only_an_anchored_index(self):
        helper = test_release_evidence.ReleaseEvidenceTests(
            methodName="test_default_policy_is_unconfigured_and_release_is_blocked"
        )
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (
                prior_index_path,
                policy_path,
                _,
                _,
                prior_index,
                policy,
            ) = helper.signed_packet(directory)
            candidate = "a" * 40
            artifact = release_packet.build_gate_artifact(
                gate="reviewer_attestation",
                candidate_commit=candidate,
                status="PASS",
                assertions=helper.assertions_for("reviewer_attestation"),
                evidence_refs=["7" * 64],
                hard_failures=[],
                executed_at=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
            )
            artifact_path = directory / "reviewer-new.json"
            artifact_path.write_bytes(release_evidence.canonical_bytes(artifact))
            payload = release_packet.build_receipt_payload(
                artifact=artifact,
                issued_at=datetime(2026, 1, 1, 0, 11, tzinfo=timezone.utc),
                nonce="reviewer-new-receipt-0001",
            )
            payload_path = directory / "reviewer-new.payload.json"
            payload_path.write_bytes(release_evidence.canonical_bytes(payload))
            signature_path = directory / "reviewer-new.signature.bin"
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(directory / "reviewer_attestation.private.pem"),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-out",
                    str(signature_path),
                ],
                check=True,
                capture_output=True,
            )
            key_id = next(
                authority["key_id"]
                for authority in policy["authorities"]
                if authority["role"] == "reviewer_authority"
            )
            receipt = release_packet.assemble_receipt(
                payload=payload,
                signature=signature_path.read_bytes(),
                key_id=key_id,
                policy_path=policy_path,
                expected_policy_sha256=policy["policy_sha256"],
            )
            receipt_path = directory / "reviewer-new.receipt.json"
            receipt_path.write_bytes(release_evidence.canonical_bytes(receipt))
            output_path = directory / "index-v2.json"
            index = release_packet.advance_index(
                prior_index_path=prior_index_path,
                artifact_path=artifact_path,
                receipt_path=receipt_path,
                output_path=output_path,
                policy_path=policy_path,
                expected_policy_sha256=policy["policy_sha256"],
                expected_prior_index_sha256=prior_index["index_sha256"],
                candidate_commit=candidate,
            )
            self.assertEqual(index["gates"]["reviewer_attestation"]["status"], "PASS")
            verified = release_evidence.verify(
                output_path,
                policy_path,
                candidate,
                policy["policy_sha256"],
                index["index_sha256"],
            )
            self.assertEqual(verified["verification_status"], "pass")
            self.assertEqual(verified["verified_gate_count"], 2)
            with self.assertRaises(release_evidence.ReleaseEvidenceError):
                release_packet.advance_index(
                    prior_index_path=prior_index_path,
                    artifact_path=artifact_path,
                    receipt_path=receipt_path,
                    output_path=directory / "index-wrong-anchor.json",
                    policy_path=policy_path,
                    expected_policy_sha256=policy["policy_sha256"],
                    expected_prior_index_sha256="0" * 64,
                    candidate_commit=candidate,
                )

    def test_passing_gate_cannot_be_built_from_incomplete_assertions(self):
        with self.assertRaises(release_evidence.ReleaseEvidenceError):
            release_packet.build_gate_artifact(
                gate="privacy_preflight",
                candidate_commit="a" * 40,
                status="PASS",
                assertions={"storage_map_verified": True},
                evidence_refs=["8" * 64],
                hard_failures=[],
                executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
