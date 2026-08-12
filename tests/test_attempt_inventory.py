from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import attempt_inventory  # noqa: E402
import campaign  # noqa: E402
import release_packet  # noqa: E402
import target_session  # noqa: E402
from test_target_session import (  # noqa: E402
    ADAPTER,
    NOW,
    SUITE,
    FakeClock,
    config,
    review_for,
)

WITNESS = ROOT / "tests/fixtures/attempt_witness.py"
CAMPAIGN_ID = "campaign-attempts-0001"


class AttemptInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._temporary.name)
        cls.private_key = cls.directory / "attempt.private.pem"
        cls.public_key = cls.directory / "attempt.public.pem"
        cls.state_path = cls.directory / "witness-state.json"
        subprocess.run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "ED25519",
                "-out",
                str(cls.private_key),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(cls.private_key),
                "-pubout",
                "-out",
                str(cls.public_key),
            ],
            check=True,
            capture_output=True,
        )
        cls.cfg = config()
        roles = (
            ("behavioral_qualification", "behavioral_evidence_authority"),
            ("reviewer_attestation", "reviewer_authority"),
            ("attempt_inventory", "attempt_log_authority"),
            ("holdout", "holdout_authority"),
            ("privacy_preflight", "privacy_authority"),
            ("bilingual_review", "bilingual_review_authority"),
            ("pilot", "pilot_authority"),
            ("independent_release_review", "independent_release_reviewer"),
            ("owner_promotion", "owner"),
        )
        authorities = []
        for index, (gate, role) in enumerate(roles, start=1):
            is_attempt = gate == "attempt_inventory"
            authorities.append(
                {
                    "key_id": "attempt-witness" if is_attempt else f"unused-key-{index}",
                    "role": role,
                    "public_key_path": (
                        cls.public_key.name if is_attempt else f"unused-{index}.pem"
                    ),
                    "public_key_sha256": (
                        hashlib.sha256(cls.public_key.read_bytes()).hexdigest()
                        if is_attempt
                        else format(index, "x") * 64
                    ),
                    "allowed_gates": [gate],
                }
            )
        policy = {
            "schema_version": "1.0",
            "status": "CONFIGURED",
            "candidate_commit": cls.cfg["source_commit"],
            "frozen_at": "2026-08-12T12:00:00Z",
            "attempt_campaign_id": CAMPAIGN_ID,
            "target_config_sha256": target_session._digest(cls.cfg),
            "holdout_seal_sha256": "2" * 64,
            "privacy_host_identity_sha256": "3" * 64,
            "pilot_protocol_sha256": "4" * 64,
            "authorities": authorities,
        }
        policy["policy_sha256"] = attempt_inventory.digest(policy)
        cls.policy = policy
        cls.policy_path = cls.directory / "policy.json"
        cls.policy_path.write_bytes(attempt_inventory.canonical_bytes(policy))
        cls.results_directory = cls.directory / "results"
        cls.results_directory.mkdir()
        cls.results: list[dict] = []
        cls.result_paths: list[Path] = []
        for run_index, identity in enumerate(cls.cfg["run_plan"]):
            session = target_session.TargetSession(
                suite=SUITE,
                config=cls.cfg,
                case_id=identity["case_id"],
                system_id=identity["system_id"],
                variant_id=identity["variant_id"],
                repetition=identity["repetition"],
                clock=FakeClock(),
            )
            provider = target_session.FrozenStdioProvider(
                config=cls.cfg,
                adapter_path=ADAPTER,
                environment={},
                clock=FakeClock(),
            )
            try:
                while session.status != "COMPLETE":
                    completion = session.capture(provider)
                    session.import_review(review_for(session, completion))
            finally:
                provider.close()
            result = target_session.finalize_session(session)
            path = cls.results_directory / f"result-{run_index:03d}.json"
            path.write_bytes(attempt_inventory.canonical_bytes(result))
            cls.results.append(result)
            cls.result_paths.append(path)
        cls.manifest_path = cls.results_directory / "manifest.json"
        manifest = campaign.build_result_manifest(
            result_paths=cls.result_paths,
            manifest_path=cls.manifest_path,
            suite=SUITE,
            config=cls.cfg,
            clock=FakeClock(),
        )
        cls.manifest_path.write_bytes(attempt_inventory.canonical_bytes(manifest))
        cls.manifest = manifest
        cls.ledger = cls.directory / "ledger"
        cls.ledger.mkdir()
        with patch.dict(
            os.environ,
            {
                "PGC_TEST_WITNESS_PRIVATE_KEY": str(cls.private_key),
                "PGC_TEST_WITNESS_STATE": str(cls.state_path),
            },
        ):
            prior = cls._append(
                None,
                "CAMPAIGN_REGISTERED",
                {
                    "kind": "CAMPAIGN_REGISTERED",
                    "planned_run_count": len(cls.cfg["run_plan"]),
                },
            )
            for identity, result, manifest_entry in zip(
                cls.cfg["run_plan"], cls.results, cls.manifest["results"], strict=True
            ):
                for capture_index, capture in enumerate(result["captures"]):
                    attempt_id = "attempt-" + hashlib.sha256(
                        f"{identity}-{capture_index}".encode()
                    ).hexdigest()[:32]
                    prior = cls._append(
                        prior,
                        "CAPTURE_STARTED",
                        {
                            "kind": "CAPTURE_STARTED",
                            "attempt_id": attempt_id,
                            "run_identity": identity,
                            "turn_id": capture["turn_id"],
                            "session_before_sha256": hashlib.sha256(
                                f"session-{attempt_id}".encode()
                            ).hexdigest(),
                            "request_sha256": capture["request_sha256"],
                        },
                    )
                    prior = cls._append(
                        prior,
                        "CAPTURE_FINISHED",
                        {
                            "kind": "CAPTURE_FINISHED",
                            "attempt_id": attempt_id,
                            "outcome": "SUCCESS",
                            "completion_sha256": capture["completion_sha256"],
                            "provider_response_id": capture["provider_response_id"],
                            "failure_code": None,
                        },
                    )
                prior = cls._append(
                    prior,
                    "RUN_FINALIZED",
                    {
                        "kind": "RUN_FINALIZED",
                        "run_identity": identity,
                        "result_relative_path": manifest_entry["relative_path"],
                        "result_sha256": manifest_entry["sha256"],
                    },
                )
            capture_count = sum(len(result["captures"]) for result in cls.results)
            prior = cls._append(
                prior,
                "CAMPAIGN_SEALED",
                {
                    "kind": "CAMPAIGN_SEALED",
                    "capture_attempt_count": capture_count,
                    "finalized_run_count": len(cls.results),
                    "result_manifest_sha256": manifest["manifest_sha256"],
                    "provider_access_enforced": True,
                    "provider_access_control_sha256": "b" * 64,
                    "all_artifacts_preserved": True,
                    "artifact_inventory_sha256": "c" * 64,
                },
            )
        cls.index_path = prior
        cls.index = json.loads(prior.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    @classmethod
    def _append(cls, prior: Path | None, event_type: str, payload: dict) -> Path:
        sequence = 0
        if prior is not None:
            sequence = len(json.loads(prior.read_text(encoding="utf-8"))["entries"])
        event_path = cls.ledger / f"event-{sequence:06d}.json"
        receipt_path = cls.ledger / f"receipt-{sequence:06d}.json"
        index_path = cls.ledger / f"index-{sequence:06d}.json"
        attempt_inventory.append_witnessed_event(
            config=cls.cfg,
            campaign_id=CAMPAIGN_ID,
            prior_index_path=prior,
            event_type=event_type,
            payload=payload,
            witness_adapter=WITNESS,
            policy_path=cls.policy_path,
            expected_policy_sha256=cls.policy["policy_sha256"],
            event_output=event_path,
            receipt_output=receipt_path,
            index_output=index_path,
            clock=FakeClock(),
        )
        return index_path

    def verify(self, *, head: str | None = None, count: int | None = None):
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            return attempt_inventory.verify_inventory(
                index_path=self.index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=self.policy_path,
                expected_policy_sha256=self.policy["policy_sha256"],
                expected_head_sha256=head or self.index["entries"][-1]["event_sha256"],
                expected_event_count=(
                    len(self.index["entries"]) if count is None else count
                ),
                clock=FakeClock(),
            )

    def test_complete_external_chain_reconciles_exact_result_captures(self):
        result = self.verify()
        self.assertEqual(result["verification_status"], "pass")
        self.assertEqual(result["inventory_status"], "PASS")
        self.assertTrue(result["qualification_ready"])
        self.assertTrue(result["assertions"]["external_witness_receipts_verified"])
        self.assertEqual(result["provider_access_control_sha256"], "b" * 64)
        self.assertEqual(result["artifact_inventory_sha256"], "c" * 64)
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            artifact = release_packet.attempt_artifact(
                index_path=self.index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=self.policy_path,
                expected_policy_sha256=self.policy["policy_sha256"],
                expected_head_sha256=self.index["entries"][-1]["event_sha256"],
                expected_event_count=len(self.index["entries"]),
                candidate_commit=self.cfg["source_commit"],
                executed_at=NOW,
                verification_clock=FakeClock(),
            )
        self.assertEqual(artifact["status"], "PASS")
        self.assertEqual(artifact["evidence_refs"][0], result["inventory_sha256"])

    def test_external_head_and_count_are_mandatory_current_state_anchors(self):
        result = self.verify(head="0" * 64, count=len(self.index["entries"]) - 1)
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("external witness head/count" in error for error in result["errors"])
        )

    def test_owner_anchored_campaign_epoch_cannot_be_reset(self):
        policy = dict(self.policy)
        policy["attempt_campaign_id"] = "campaign-other-0001"
        policy["policy_sha256"] = attempt_inventory.object_hash(
            policy, "policy_sha256"
        )
        policy_path = self.directory / "policy-other-campaign.json"
        policy_path.write_bytes(attempt_inventory.canonical_bytes(policy))
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            result = attempt_inventory.verify_inventory(
                index_path=self.index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=policy_path,
                expected_policy_sha256=policy["policy_sha256"],
                expected_head_sha256=self.index["entries"][-1]["event_sha256"],
                expected_event_count=len(self.index["entries"]),
                clock=FakeClock(),
            )
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("owner-anchored attempt epoch" in error for error in result["errors"])
        )

    def test_target_config_cannot_be_substituted_after_policy_freeze(self):
        policy = dict(self.policy)
        policy["target_config_sha256"] = "0" * 64
        policy["policy_sha256"] = attempt_inventory.object_hash(
            policy, "policy_sha256"
        )
        policy_path = self.directory / "policy-other-config.json"
        policy_path.write_bytes(attempt_inventory.canonical_bytes(policy))
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            result = attempt_inventory.verify_inventory(
                index_path=self.index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=policy_path,
                expected_policy_sha256=policy["policy_sha256"],
                expected_head_sha256=self.index["entries"][-1]["event_sha256"],
                expected_event_count=len(self.index["entries"]),
                clock=FakeClock(),
            )
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("owner-frozen release policy" in error for error in result["errors"])
        )

    def test_attempt_chain_must_follow_the_owner_anchored_policy_freeze(self):
        policy = dict(self.policy)
        policy["frozen_at"] = "2026-08-12T13:00:00Z"
        policy["policy_sha256"] = attempt_inventory.object_hash(
            policy, "policy_sha256"
        )
        policy_path = self.directory / "policy-after-events.json"
        policy_path.write_bytes(attempt_inventory.canonical_bytes(policy))

        def later_clock():
            return datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)

        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            result = attempt_inventory.verify_inventory(
                index_path=self.index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=policy_path,
                expected_policy_sha256=policy["policy_sha256"],
                expected_head_sha256=self.index["entries"][-1]["event_sha256"],
                expected_event_count=len(self.index["entries"]),
                clock=later_clock,
            )
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("predates the owner-anchored policy freeze" in error for error in result["errors"])
        )

    def test_manifested_result_tampering_fails_closed(self):
        original = self.result_paths[0].read_bytes()
        try:
            self.result_paths[0].write_bytes(original + b" ")
            result = self.verify()
        finally:
            self.result_paths[0].write_bytes(original)
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("result file sha256 mismatch" in error for error in result["errors"])
        )

    def test_same_logical_turn_cannot_be_retried_under_a_new_attempt_id(self):
        ledger = self.directory / "retry-ledger"
        ledger.mkdir()
        state = self.directory / "retry-witness-state.json"
        capture = self.results[0]["captures"][0]
        identity = self.cfg["run_plan"][0]

        def append(prior: Path | None, event_type: str, payload: dict) -> Path:
            sequence = 0 if prior is None else len(
                json.loads(prior.read_text(encoding="utf-8"))["entries"]
            )
            index_path = ledger / f"index-{sequence:06d}.json"
            attempt_inventory.append_witnessed_event(
                config=self.cfg,
                campaign_id=CAMPAIGN_ID,
                prior_index_path=prior,
                event_type=event_type,
                payload=payload,
                witness_adapter=WITNESS,
                policy_path=self.policy_path,
                expected_policy_sha256=self.policy["policy_sha256"],
                event_output=ledger / f"event-{sequence:06d}.json",
                receipt_output=ledger / f"receipt-{sequence:06d}.json",
                index_output=index_path,
                clock=FakeClock(),
            )
            return index_path

        with patch.dict(
            os.environ,
            {
                "PGC_TEST_WITNESS_PRIVATE_KEY": str(self.private_key),
                "PGC_TEST_WITNESS_STATE": str(state),
            },
        ):
            prior = append(
                None,
                "CAMPAIGN_REGISTERED",
                {
                    "kind": "CAMPAIGN_REGISTERED",
                    "planned_run_count": len(self.cfg["run_plan"]),
                },
            )
            for suffix in ("1" * 32, "2" * 32):
                attempt_id = "attempt-" + suffix
                prior = append(
                    prior,
                    "CAPTURE_STARTED",
                    {
                        "kind": "CAPTURE_STARTED",
                        "attempt_id": attempt_id,
                        "run_identity": identity,
                        "turn_id": capture["turn_id"],
                        "session_before_sha256": suffix * 2,
                        "request_sha256": capture["request_sha256"],
                    },
                )
                prior = append(
                    prior,
                    "CAPTURE_FINISHED",
                    {
                        "kind": "CAPTURE_FINISHED",
                        "attempt_id": attempt_id,
                        "outcome": "SUCCESS",
                        "completion_sha256": capture["completion_sha256"],
                        "provider_response_id": "retry-" + suffix,
                        "failure_code": None,
                    },
                )
        index = json.loads(prior.read_text(encoding="utf-8"))
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            result = attempt_inventory.verify_inventory(
                index_path=prior,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=self.policy_path,
                expected_policy_sha256=self.policy["policy_sha256"],
                expected_head_sha256=index["entries"][-1]["event_sha256"],
                expected_event_count=len(index["entries"]),
                clock=FakeClock(),
            )
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("capture retry" in error for error in result["errors"])
        )

    def test_recomputed_local_hashes_cannot_hide_a_bad_witness_signature(self):
        copied = self.directory / "tampered-ledger"
        shutil.copytree(self.ledger, copied)
        index_path = copied / self.index_path.name
        index = json.loads(index_path.read_text(encoding="utf-8"))
        receipt_path = copied / index["entries"][0]["receipt_path"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        signature = receipt["signature_base64"]
        receipt["signature_base64"] = (
            ("A" if signature[0] != "A" else "B") + signature[1:]
        )
        receipt_bytes = attempt_inventory.canonical_bytes(receipt)
        receipt_path.write_bytes(receipt_bytes)
        index["entries"][0]["receipt_sha256"] = hashlib.sha256(
            receipt_bytes
        ).hexdigest()
        index["index_sha256"] = attempt_inventory.object_hash(index, "index_sha256")
        index_path.write_bytes(attempt_inventory.canonical_bytes(index))
        with patch.object(campaign, "_require_full_suite_scope", return_value=None):
            result = attempt_inventory.verify_inventory(
                index_path=index_path,
                config=self.cfg,
                suite=SUITE,
                result_manifest_path=self.manifest_path,
                policy_path=self.policy_path,
                expected_policy_sha256=self.policy["policy_sha256"],
                expected_head_sha256=index["entries"][-1]["event_sha256"],
                expected_event_count=len(index["entries"]),
                clock=FakeClock(),
            )
        self.assertFalse(result["qualification_ready"])
        self.assertTrue(
            any("signature verification failed" in error for error in result["errors"])
        )

    def test_release_gate_rejects_legacy_self_asserted_attempt_shape(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import release_evidence

        assertions = {
            "immutable_inventory": True,
            "all_attempts_accounted_for": True,
            "submitted_results_complete": True,
            "omitted_attempt_count": 0,
            "attempt_count": 9,
            "submitted_result_count": 9,
        }
        errors = release_evidence.assertion_errors("attempt_inventory", assertions)
        self.assertTrue(any("provider_access_enforced" in error for error in errors))
        self.assertTrue(
            any("external_witness_receipts_verified" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
