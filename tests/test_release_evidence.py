from __future__ import annotations

import base64
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402


class ReleaseEvidenceTests(unittest.TestCase):
    def write_json(self, path: Path, value: dict) -> bytes:
        data = release_evidence.canonical_bytes(value)
        path.write_bytes(data)
        return data

    def assertions_for(self, gate: str) -> dict:
        return {
            "behavioral_qualification": {
                "submitted_matrix_status": "conditional_pass",
                "all_systems_automated_pass": True,
                "all_systems_zero_hard_failures": True,
                "reviewer_agreement_pass": True,
                "high_critical_scores_pass": True,
                "other_distribution_pass": True,
                "direct_noninferiority_pass": True,
                "chinese_integrity_pass": True,
            },
            "reviewer_attestation": {
                "identities_verified": True,
                "independence_verified": True,
                "calibration_verified": True,
                "reviewer_count": 2,
            },
            "attempt_inventory": {
                "immutable_inventory": True,
                "all_attempts_accounted_for": True,
                "submitted_results_complete": True,
                "omitted_attempt_count": 0,
                "attempt_count": 309,
                "submitted_result_count": 309,
            },
            "holdout": {
                "sealed": True,
                "independent_authors": True,
                "all_hard_gates_pass": True,
                "candidate_author_access": False,
                "holdout_fraction": 0.20,
                "case_count": 3,
            },
            "privacy_preflight": {
                "storage_map_verified": True,
                "encryption_verified": True,
                "no_sync_verified": True,
                "backup_restore_verified": True,
                "correction_export_deletion_verified": True,
                "bounded_retention_verified": True,
                "incident_response_tested": True,
                "unresolved_high_findings": 0,
                "named_host": "restricted-evaluation-host-1",
            },
            "bilingual_review": {
                "human_review_complete": True,
                "meaning_preserved": True,
                "safety_language_preserved": True,
                "meaning_or_safety_failures": 0,
                "fluent_reviewer_count": 2,
                "minimum_system_kappa": 0.70,
            },
            "pilot": {
                "explicit_consent": True,
                "withdrawals_honored": True,
                "deletion_requests_honored": True,
                "privacy_incidents": 0,
                "hard_safety_failures": 0,
                "dependence_failures": 0,
                "fabricated_persistence_failures": 0,
                "episode_count": 10,
                "duration_days": 28,
            },
            "independent_release_review": {
                "scope_complete": True,
                "reviewer_independent": True,
                "unresolved_findings": 0,
                "decision": "APPROVE",
            },
            "owner_promotion": {
                "all_prerequisites_verified": True,
                "decision": "PROMOTE",
            },
        }[gate]

    def signed_packet(self, directory: Path, included_gates=None):
        commit = "a" * 40
        included_gates = set(included_gates or {"behavioral_qualification"})
        keys = {}
        authorities = []
        for gate in release_evidence.GATES:
            private_key = directory / f"{gate}.private.pem"
            public_key = directory / f"{gate}.public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "pkey",
                    "-in",
                    str(private_key),
                    "-pubout",
                    "-out",
                    str(public_key),
                ],
                check=True,
                capture_output=True,
            )
            key_id = f"{gate.replace('_', '-')}-authority"
            keys[gate] = (private_key, public_key, key_id)
            authorities.append(
                {
                    "key_id": key_id,
                    "role": release_evidence.ROLE_BY_GATE[gate],
                    "public_key_path": public_key.name,
                    "public_key_sha256": hashlib.sha256(public_key.read_bytes()).hexdigest(),
                    "allowed_gates": [gate],
                }
            )
        policy = {
            "schema_version": "1.0",
            "status": "CONFIGURED",
            "candidate_commit": commit,
            "frozen_at": "2026-01-01T00:00:00Z",
            "authorities": authorities,
        }
        policy["policy_sha256"] = release_evidence.digest(policy)
        policy_path = directory / "policy.json"
        self.write_json(policy_path, policy)
        pending = {
            "status": "PENDING",
            "artifact_path": None,
            "artifact_sha256": None,
            "receipt_path": None,
            "receipt_sha256": None,
        }
        gates = {gate: copy.deepcopy(pending) for gate in release_evidence.GATES}
        artifact_paths = {}
        artifacts = {}
        for gate in release_evidence.GATES:
            if gate not in included_gates:
                continue
            evidence_refs = [hashlib.sha256(gate.encode()).hexdigest()]
            if gate == "owner_promotion":
                evidence_refs = [
                    artifacts[prior]["artifact_sha256"]
                    for prior in release_evidence.GATES[:-1]
                ]
            artifact = {
                "schema_version": "1.0",
                "gate": gate,
                "candidate_commit": commit,
                "status": "PASS",
                "executed_at": "2026-01-01T00:01:00Z",
                "hard_failures": [],
                "assertions": self.assertions_for(gate),
                "evidence_refs": evidence_refs,
            }
            artifact["artifact_sha256"] = release_evidence.digest(artifact)
            artifact_path = directory / f"{gate}.json"
            self.write_json(artifact_path, artifact)
            private_key, _, key_id = keys[gate]
            payload = {
                "domain": "personal-growth-copilot-release-gate-v1",
                "gate": gate,
                "candidate_commit": commit,
                "artifact_sha256": artifact["artifact_sha256"],
                "outcome": "PASS",
                "issued_at": "2026-01-01T00:02:00Z",
                "nonce": f"{gate}-receipt-00000001",
            }
            payload_path = directory / f"{gate}.payload.json"
            payload_path.write_bytes(release_evidence.canonical_bytes(payload))
            signature_path = directory / f"{gate}.signature.bin"
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(private_key),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-out",
                    str(signature_path),
                ],
                check=True,
                capture_output=True,
            )
            receipt = {
                "schema_version": "1.0",
                "key_id": key_id,
                "payload": payload,
                "signature_base64": base64.b64encode(signature_path.read_bytes()).decode(),
            }
            receipt_path = directory / f"{gate}.receipt.json"
            receipt_bytes = self.write_json(receipt_path, receipt)
            gates[gate] = {
                "status": "PASS",
                "artifact_path": artifact_path.name,
                "artifact_sha256": artifact["artifact_sha256"],
                "receipt_path": receipt_path.name,
                "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            }
            artifact_paths[gate] = artifact_path
            artifacts[gate] = artifact
        index = {
            "schema_version": "1.0",
            "candidate_commit": commit,
            "trust_policy_sha256": policy["policy_sha256"],
            "overall_status": (
                "PROMOTED"
                if included_gates == set(release_evidence.GATES)
                else "BLOCKED"
            ),
            "gates": gates,
        }
        index["index_sha256"] = release_evidence.digest(index)
        index_path = directory / "index.json"
        self.write_json(index_path, index)
        return index_path, policy_path, artifact_paths, artifacts, index, policy

    def test_default_policy_is_unconfigured_and_release_is_blocked(self):
        result = release_evidence.verify(
            ROOT / "release/evidence-index.json",
            ROOT / "release/trust-policy.json",
            "0" * 40,
            "248b39af6fe41f4c81ff7dd44aa8d5d15ef09a27ebb137c6a21b1c5f075f179c",
        )
        self.assertEqual(result["release_status"], "BLOCKED")
        self.assertFalse(result["qualification_update_allowed"])
        self.assertIn("trust policy is unconfigured", result["errors"])

    def test_duplicate_keys_and_non_finite_numbers_are_rejected(self):
        with self.assertRaises(release_evidence.ReleaseEvidenceError):
            release_evidence.json_object(b'{"gate":"one","gate":"two"}', "artifact")
        with self.assertRaises(release_evidence.ReleaseEvidenceError):
            release_evidence.json_object(b'{"minimum_system_kappa":NaN}', "artifact")

    def test_valid_role_scoped_signature_verifies_but_one_gate_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory_name:
            index_path, policy_path, _, _, _, _ = self.signed_packet(
                Path(directory_name)
            )
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            result = release_evidence.verify(
                index_path, policy_path, "a" * 40, policy["policy_sha256"]
            )
            self.assertEqual(result["verification_status"], "pass")
            self.assertEqual(result["release_status"], "BLOCKED")
            self.assertEqual(result["verified_gate_count"], 1)
            self.assertFalse(result["qualification_update_allowed"])

    def test_tampered_artifact_and_false_green_assertion_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            index_path, policy_path, artifact_paths, _, index, _ = self.signed_packet(directory)
            artifact_path = artifact_paths["behavioral_qualification"]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["assertions"]["all_systems_zero_hard_failures"] = False
            artifact["artifact_sha256"] = release_evidence.object_hash(
                artifact, "artifact_sha256"
            )
            self.write_json(artifact_path, artifact)
            index["gates"]["behavioral_qualification"]["artifact_sha256"] = artifact[
                "artifact_sha256"
            ]
            index["index_sha256"] = release_evidence.object_hash(
                index, "index_sha256"
            )
            self.write_json(index_path, index)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            result = release_evidence.verify(
                index_path, policy_path, "a" * 40, policy["policy_sha256"]
            )
            self.assertEqual(result["verification_status"], "fail")
            self.assertEqual(result["release_status"], "BLOCKED")
            self.assertTrue(
                any(
                    "all_systems_zero_hard_failures" in error
                    or "another artifact" in error
                    for error in result["errors"]
                )
            )

    def test_all_nine_signed_gates_are_required_before_promotion(self):
        with tempfile.TemporaryDirectory() as directory_name:
            index_path, policy_path, _, _, _, _ = self.signed_packet(
                Path(directory_name), included_gates=set(release_evidence.GATES)
            )
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            result = release_evidence.verify(
                index_path, policy_path, "a" * 40, policy["policy_sha256"]
            )
            self.assertEqual(result["verification_status"], "pass")
            self.assertEqual(result["release_status"], "PROMOTED")
            self.assertEqual(result["verified_gate_count"], 9)
            self.assertTrue(result["qualification_update_allowed"])

    def test_signed_invalidation_is_valid_evidence_but_blocks_release(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            index_path, policy_path, artifact_paths, _, index, policy = self.signed_packet(
                directory
            )
            gate = "behavioral_qualification"
            artifact_path = artifact_paths[gate]
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["status"] = "INVALIDATED"
            artifact["hard_failures"] = ["attempt inventory was disclosed early"]
            artifact["artifact_sha256"] = release_evidence.object_hash(
                artifact, "artifact_sha256"
            )
            self.write_json(artifact_path, artifact)
            receipt_path = directory / index["gates"][gate]["receipt_path"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["payload"]["artifact_sha256"] = artifact["artifact_sha256"]
            receipt["payload"]["outcome"] = "INVALIDATED"
            payload_path = directory / "invalidation.payload.json"
            payload_path.write_bytes(
                release_evidence.canonical_bytes(receipt["payload"])
            )
            signature_path = directory / "invalidation.signature.bin"
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(directory / f"{gate}.private.pem"),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-out",
                    str(signature_path),
                ],
                check=True,
                capture_output=True,
            )
            receipt["signature_base64"] = base64.b64encode(
                signature_path.read_bytes()
            ).decode()
            receipt_bytes = self.write_json(receipt_path, receipt)
            index["gates"][gate].update(
                {
                    "status": "INVALIDATED",
                    "artifact_sha256": artifact["artifact_sha256"],
                    "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                }
            )
            index["index_sha256"] = release_evidence.object_hash(
                index, "index_sha256"
            )
            self.write_json(index_path, index)
            result = release_evidence.verify(
                index_path,
                policy_path,
                "a" * 40,
                policy["policy_sha256"],
            )
            self.assertEqual(result["verification_status"], "pass")
            self.assertEqual(result["release_status"], "BLOCKED")
            self.assertFalse(result["qualification_update_allowed"])

    def test_authority_key_aliases_and_candidate_substitution_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            index_path, policy_path, _, _, index, policy = self.signed_packet(directory)
            policy["authorities"][1]["public_key_path"] = policy["authorities"][0][
                "public_key_path"
            ]
            policy["authorities"][1]["public_key_sha256"] = policy["authorities"][0][
                "public_key_sha256"
            ]
            policy["policy_sha256"] = release_evidence.object_hash(
                policy, "policy_sha256"
            )
            self.write_json(policy_path, policy)
            index["trust_policy_sha256"] = policy["policy_sha256"]
            index["index_sha256"] = release_evidence.object_hash(
                index, "index_sha256"
            )
            self.write_json(index_path, index)
            result = release_evidence.verify(
                index_path,
                policy_path,
                "b" * 40,
                "f" * 64,
            )
            self.assertEqual(result["verification_status"], "fail")
            self.assertEqual(result["release_status"], "BLOCKED")
            self.assertTrue(
                any("public keys must be unique" in error for error in result["errors"])
            )
            self.assertTrue(
                any("checked-out candidate commit" in error for error in result["errors"])
            )
            self.assertTrue(
                any("owner trust anchor" in error for error in result["errors"])
            )


if __name__ == "__main__":
    unittest.main()
