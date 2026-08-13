from __future__ import annotations

import copy
import base64
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402
import release_packet  # noqa: E402


CANDIDATE = "a" * 40
FREEZE = datetime(2026, 8, 12, tzinfo=timezone.utc)
HASH = "1" * 64


def write_json(path: Path, value: dict) -> str:
    data = release_evidence.canonical_bytes(value)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def write_evidence(directory: Path, name: str) -> tuple[str, str]:
    path = directory / name
    data = ("evidence:" + name).encode()
    path.write_bytes(data)
    return path.name, hashlib.sha256(data).hexdigest()


def signing_key(directory: Path, name: str) -> tuple[Path, str, str]:
    private_key = directory / f"{name}.private.pem"
    public_key = directory / f"{name}.public.pem"
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
    return private_key, public_key.name, hashlib.sha256(public_key.read_bytes()).hexdigest()


def sign_payload(directory: Path, name: str, payload: dict, private_key: Path) -> str:
    payload_path = directory / f"{name}.payload.json"
    signature_path = directory / f"{name}.signature.bin"
    payload_path.write_bytes(release_evidence.canonical_bytes(payload))
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
    return base64.b64encode(signature_path.read_bytes()).decode("ascii")


def scores(offset: int = 0) -> dict[str, int]:
    names = (
        "contract_and_focus",
        "reflective_accuracy",
        "inquiry_quality",
        "context_model_integrity",
        "recommendation_fit",
        "experiment_quality",
        "agency_and_challenge",
        "continuity_and_privacy",
        "language_and_specificity",
        "anti_dependence",
        "safety_and_scope",
    )
    return {name: 4 + ((index + offset) % 2) for index, name in enumerate(names)}


class ExternalGateSourceTests(unittest.TestCase):
    def privacy_source(self, directory: Path) -> dict:
        private_key, public_key_path, public_key_sha256 = signing_key(
            directory, "privacy-audit-witness"
        )
        checks = []
        for check_id in (
            "storage_map",
            "encryption",
            "no_sync",
            "backup_restore",
            "correction_export_deletion",
            "bounded_retention",
            "incident_response",
        ):
            evidence_path, evidence_sha256 = write_evidence(
                directory, f"privacy-{check_id}.evidence"
            )
            checks.append(
                {
                    "check_id": check_id,
                    "status": "PASS",
                    "executed_at": "2026-08-13T00:00:00Z",
                    "evidence_path": evidence_path,
                    "evidence_sha256": evidence_sha256,
                }
            )
        host_record = {
            "schema_version": "1.0",
            "evidence_class": "privacy-host-identity",
            "named_host": "restricted-evaluation-host-1",
            "environment_id": "pgc-private-evaluation-001",
            "storage_root_sha256": release_evidence.filesystem_object_identity(directory),
            "audit_id": "privacy-audit-0000000000000001",
            "audit_public_key_path": public_key_path,
            "audit_public_key_sha256": public_key_sha256,
            "captured_at": "2026-08-12T00:00:00Z",
        }
        host_path = directory / "host-identity.json"
        host_sha256 = write_json(host_path, host_record)
        source = {
            "schema_version": "1.0",
            "evidence_class": "privacy-preflight-source",
            "candidate_commit": CANDIDATE,
            "named_host": "restricted-evaluation-host-1",
            "host_identity_path": host_path.name,
            "host_identity_sha256": host_sha256,
            "completed_at": "2026-08-14T00:00:00Z",
            "retention_days": 30,
            "checks": checks,
            "findings": [],
        }
        source["audit_sha256"] = release_evidence.selected_hash(
            source,
            (
                "candidate_commit",
                "named_host",
                "host_identity_sha256",
                "completed_at",
                "retention_days",
                "checks",
                "findings",
            ),
        )
        source["audit_event_count"] = len(source["checks"]) + len(source["findings"])
        payload = {
            "domain": "pgc-privacy-audit-witness-v1",
            "candidate_commit": CANDIDATE,
            "audit_id": host_record["audit_id"],
            "host_identity_sha256": host_sha256,
            "audit_sha256": source["audit_sha256"],
            "event_count": source["audit_event_count"],
            "completed_at": source["completed_at"],
            "nonce": "privacy-audit-nonce-0001",
        }
        source["audit_receipt"] = {
            "payload": payload,
            "signature_base64": sign_payload(
                directory, "privacy-audit", payload, private_key
            ),
        }
        return source

    def holdout_source(self, directory: Path) -> dict:
        private_key, witness_key_path, witness_key_sha256 = signing_key(
            directory, "holdout-attempt-witness"
        )
        case_ids = [f"holdout-case-{index}" for index in range(1, 5)]
        ciphertext_path, ciphertext_sha256 = write_evidence(directory, "holdout.enc")
        schema_path, schema_sha256 = write_evidence(directory, "holdout-schema.json")
        authors = []
        for index in (1, 2):
            identity_path, identity_sha256 = write_evidence(
                directory, f"author-{index}-identity.evidence"
            )
            independence_path, independence_sha256 = write_evidence(
                directory, f"author-{index}-independence.evidence"
            )
            authorship_path, authorship_sha256 = write_evidence(
                directory, f"author-{index}-authorship.evidence"
            )
            authors.append(
                {
                    "author_id": f"author-{index:016x}",
                    "subject_sha256": str(index) * 64,
                    "identity_evidence_path": identity_path,
                    "identity_evidence_sha256": identity_sha256,
                    "independence_evidence_path": independence_path,
                    "independence_evidence_sha256": independence_sha256,
                    "authorship_evidence_path": authorship_path,
                    "authorship_evidence_sha256": authorship_sha256,
                    "independence_verified": True,
                }
            )
        results = []
        for index, case_id in enumerate(case_ids, start=1):
            transcript_path = directory / f"holdout-transcript-{index}.json"
            transcript = release_evidence.canonical_bytes(
                {"case_id": case_id, "turns": [{"role": "assistant", "content": "bounded"}]}
            )
            transcript_path.write_bytes(transcript)
            result = {
                "schema_version": "1.0",
                "evidence_class": "holdout-case-result",
                "candidate_commit": CANDIDATE,
                "case_id": case_id,
                "completed_at": "2026-08-15T00:00:00Z",
                "automated_status": "PASS",
                "hard_failure_codes": [],
                "transcript_path": transcript_path.name,
                "transcript_sha256": hashlib.sha256(transcript).hexdigest(),
            }
            result["result_sha256"] = release_evidence.digest(result)
            result_path = directory / f"holdout-result-{index}.json"
            result_file_sha256 = write_json(result_path, result)
            event = {
                "sequence": 0,
                "previous_event_sha256": None,
                "attempt_id": f"attempt-{index:032x}",
                "occurred_at": "2026-08-15T00:00:00Z",
                "outcome": "PASS",
                "result_sha256": result["result_sha256"],
            }
            event["event_sha256"] = release_evidence.digest(event)
            attempt = {
                "schema_version": "1.0",
                "evidence_class": "holdout-attempt-inventory",
                "candidate_commit": CANDIDATE,
                "case_id": case_id,
                "events": [event],
            }
            attempt["ledger_sha256"] = release_evidence.selected_hash(
                attempt,
                (
                    "schema_version",
                    "evidence_class",
                    "candidate_commit",
                    "case_id",
                    "events",
                ),
            )
            payload = {
                "domain": "pgc-holdout-attempt-witness-v1",
                "candidate_commit": CANDIDATE,
                "case_id": case_id,
                "ledger_sha256": attempt["ledger_sha256"],
                "event_count": 1,
                "head_event_sha256": event["event_sha256"],
                "issued_at": "2026-08-15T00:00:00Z",
                "nonce": f"holdout-attempt-nonce-{index:04d}",
            }
            attempt["witness_receipt"] = {
                "payload": payload,
                "signature_base64": sign_payload(
                    directory, f"holdout-attempt-{index}", payload, private_key
                ),
            }
            attempt["attempt_sha256"] = release_evidence.digest(attempt)
            attempt_path = directory / f"holdout-attempt-{index}.json"
            attempt_file_sha256 = write_json(attempt_path, attempt)
            results.append(
                {
                    "case_id": case_id,
                    "result_path": result_path.name,
                    "result_file_sha256": result_file_sha256,
                    "result_sha256": result["result_sha256"],
                    "attempt_inventory_path": attempt_path.name,
                    "attempt_inventory_file_sha256": attempt_file_sha256,
                    "attempt_inventory_sha256": attempt["attempt_sha256"],
                }
            )
        seal = {
            "schema_version": "1.0",
            "evidence_class": "holdout-seal",
            "candidate_commit": CANDIDATE,
            "sealed_at": "2026-08-12T00:00:00Z",
            "public_case_count": 13,
            "sealed_case_ids": case_ids,
            "ciphertext_path": ciphertext_path,
            "ciphertext_sha256": ciphertext_sha256,
            "case_schema_path": schema_path,
            "case_schema_sha256": schema_sha256,
            "witness_public_key_path": witness_key_path,
            "witness_public_key_sha256": witness_key_sha256,
            "authors": authors,
        }
        seal["seal_sha256"] = release_evidence.digest(seal)
        seal_path = directory / "holdout-seal.json"
        seal_file_sha256 = write_json(seal_path, seal)
        access_audit = {
            "schema_version": "1.0",
            "evidence_class": "holdout-access-audit",
            "candidate_commit": CANDIDATE,
            "holdout_seal_sha256": seal["seal_sha256"],
            "generated_at": "2026-08-15T00:00:00Z",
            "events": [],
        }
        access_audit["audit_sha256"] = release_evidence.digest(access_audit)
        audit_path = directory / "holdout-access-audit.json"
        audit_file_sha256 = write_json(audit_path, access_audit)
        return {
            "schema_version": "1.0",
            "evidence_class": "holdout-source",
            "candidate_commit": CANDIDATE,
            "seal_path": seal_path.name,
            "seal_file_sha256": seal_file_sha256,
            "seal_sha256": seal["seal_sha256"],
            "revealed_at": "2026-08-14T00:00:00Z",
            "completed_at": "2026-08-15T00:00:00Z",
            "access_audit_path": audit_path.name,
            "access_audit_file_sha256": audit_file_sha256,
            "access_audit_sha256": access_audit["audit_sha256"],
            "results": results,
        }

    def pilot_source(self, directory: Path) -> dict:
        private_key, witness_key_path, witness_key_sha256 = signing_key(
            directory, "pilot-ledger-witness"
        )
        episode_ids = [f"episode-{index:016x}" for index in range(1, 11)]
        protocol = {
            "schema_version": "1.0",
            "evidence_class": "pilot-protocol",
            "candidate_commit": CANDIDATE,
            "preregistered_at": "2026-08-12T00:00:00Z",
            "ledger_id": "pilot-ledger-0000000000000001",
            "witness_public_key_path": witness_key_path,
            "witness_public_key_sha256": witness_key_sha256,
            "planned_episode_ids": episode_ids,
            "minimum_duration_days": 28,
            "maximum_duration_days": 56,
            "stop_categories": [
                "privacy",
                "hard_safety",
                "dependence",
                "fabricated_persistence",
            ],
        }
        protocol_path = directory / "pilot-protocol.json"
        protocol_sha256 = write_json(protocol_path, protocol)
        episodes = []
        start = datetime(2026, 8, 13, tzinfo=timezone.utc)
        offsets = (0, 3, 6, 9, 12, 15, 18, 21, 24, 28)
        for index, episode_id in enumerate(episode_ids):
            consent_path, consent_sha256 = write_evidence(
                directory, f"pilot-consent-{index}.evidence"
            )
            episode_path, episode_sha256 = write_evidence(
                directory, f"pilot-episode-{index}.evidence"
            )
            episodes.append(
                {
                    "episode_id": episode_id,
                    "scheduled_at": release_packet.timestamp(
                        start + timedelta(days=offsets[index])
                    ),
                    "closed_at": release_packet.timestamp(
                        start + timedelta(days=offsets[index], hours=1)
                    ),
                    "outcome": "COMPLETED",
                    "consent_evidence_path": consent_path,
                    "consent_evidence_sha256": consent_sha256,
                    "episode_evidence_path": episode_path,
                    "episode_evidence_sha256": episode_sha256,
                    "withdrawal_requested_at": None,
                    "withdrawal_honored_at": None,
                    "deletion_requested": False,
                    "deletion_completed_at": None,
                }
            )
        source = {
            "schema_version": "1.0",
            "evidence_class": "pilot-source",
            "candidate_commit": CANDIDATE,
            "protocol_path": protocol_path.name,
            "protocol_sha256": protocol_sha256,
            "preregistered_at": "2026-08-12T00:00:00Z",
            "started_at": "2026-08-13T00:00:00Z",
            "ended_at": "2026-09-10T01:00:00Z",
            "planned_episode_ids": episode_ids,
            "episodes": episodes,
            "incidents": [],
        }
        source["ledger_sha256"] = release_evidence.selected_hash(
            source,
            (
                "candidate_commit",
                "protocol_sha256",
                "started_at",
                "ended_at",
                "planned_episode_ids",
                "episodes",
                "incidents",
            ),
        )
        source["ledger_event_count"] = len(source["episodes"]) + len(source["incidents"])
        payload = {
            "domain": "pgc-pilot-ledger-witness-v1",
            "candidate_commit": CANDIDATE,
            "ledger_id": protocol["ledger_id"],
            "protocol_sha256": protocol_sha256,
            "ledger_sha256": source["ledger_sha256"],
            "event_count": source["ledger_event_count"],
            "completed_at": source["ended_at"],
            "nonce": "pilot-ledger-nonce-0001",
        }
        source["ledger_receipt"] = {
            "payload": payload,
            "signature_base64": sign_payload(
                directory, "pilot-ledger", payload, private_key
            ),
        }
        return source

    def reviewer_fixture(self, directory: Path):
        rubric_hash = hashlib.sha256((ROOT / "evals/rubric.md").read_bytes()).hexdigest()
        reviewer_ids = ["reviewer-0000000000000001", "reviewer-0000000000000002"]
        roster = []
        reviewer_evidence = []
        calibration_set_path, calibration_set_sha256 = write_evidence(
            directory, "reviewer-calibration-set.json"
        )
        for index, reviewer_id in enumerate(reviewer_ids, start=1):
            subject_sha256 = str(index + 6) * 64
            identity = {
                "schema_version": "1.0",
                "evidence_class": "reviewer-identity-attestation",
                "reviewer_id": reviewer_id,
                "subject_sha256": subject_sha256,
                "issuer": "independent-review-coordinator",
                "attested_at": "2026-08-12T00:00:00Z",
            }
            identity["identity_sha256"] = release_evidence.digest(identity)
            identity_file = directory / f"reviewer-{index}-identity.json"
            identity_sha256 = write_json(identity_file, identity)
            identity_path = identity_file.name
            independence_path, independence_sha256 = write_evidence(
                directory, f"reviewer-{index}-independence.evidence"
            )
            calibration_path, calibration_sha256 = write_evidence(
                directory, f"reviewer-{index}-calibration.evidence"
            )
            roster.append(
                {
                    "reviewer_id": reviewer_id,
                    "languages": ["en", "zh", "mixed"],
                    "identity_attestation_sha256": identity_sha256,
                    "independence_attestation_sha256": independence_sha256,
                    "calibration_attestation_sha256": calibration_sha256,
                }
            )
            reviewer_evidence.append(
                {
                    "reviewer_id": reviewer_id,
                    "subject_sha256": subject_sha256,
                    "languages": ["en", "zh", "mixed"],
                    "identity_evidence_path": identity_path,
                    "identity_evidence_sha256": identity_sha256,
                    "independence_evidence_path": independence_path,
                    "independence_evidence_sha256": independence_sha256,
                    "calibration_evidence_path": calibration_path,
                    "calibration_evidence_sha256": calibration_sha256,
                    "calibrated_at": "2026-08-13T00:00:00Z",
                    "identity_verified": True,
                    "independence_verified": True,
                    "calibration_passed": True,
                    "used_run_count": 3,
                }
            )
        config = {
            "source_commit": CANDIDATE,
            "review": {"rubric_sha256": rubric_hash, "reviewer_roster": roster},
        }
        config_path = directory / "target-config.json"
        config_hash = write_json(config_path, config)
        result_manifest = {"results": []}
        manifest_path = directory / "result-manifest.json"
        manifest_hash = write_json(manifest_path, result_manifest)
        results = []
        manifest_entries = []
        for index, system_id in enumerate(
            ("target", "direct_assistant", "structured_reflection"), start=1
        ):
            review_hash = format(index, "x") * 64
            result_hash = format(index + 6, "x") * 64
            review = {
                "review_sha256": review_hash,
                "reviewers": [
                    {
                        "reviewer_id": reviewer_ids[0],
                        "role": "primary_1",
                        "submitted_at": "2026-08-14T01:00:00Z",
                        "scores": scores(),
                    },
                    {
                        "reviewer_id": reviewer_ids[1],
                        "role": "primary_2",
                        "submitted_at": "2026-08-14T01:01:00Z",
                        "scores": scores(),
                    },
                ],
                "adjudication": {"events": [], "hard_failure_codes": []},
            }
            result = {
                "run": {
                    "case_id": "chinese-correction-and-consent",
                    "run_id": f"run-{index:024x}",
                    "system_id": system_id,
                },
                "reviews": [review],
            }
            results.append(result)
            manifest_entries.append({"sha256": result_hash})
        result_manifest["results"] = manifest_entries
        manifest_hash = write_json(manifest_path, result_manifest)
        reviewer_source = {
            "schema_version": "1.0",
            "evidence_class": "reviewer-attestation-source",
            "candidate_commit": CANDIDATE,
            "completed_at": "2026-08-15T00:00:00Z",
            "rubric_sha256": rubric_hash,
            "calibration_set_path": calibration_set_path,
            "calibration_set_sha256": calibration_set_sha256,
            "config_path": config_path.name,
            "config_sha256": config_hash,
            "result_manifest_path": manifest_path.name,
            "result_manifest_sha256": manifest_hash,
            "reviewers": reviewer_evidence,
        }
        return reviewer_source, results, manifest_entries

    def verify(self, gate: str, source: dict, directory: Path):
        bindings = {
            "target_config_sha256": source.get("config_sha256"),
            "holdout_seal_sha256": (
                source["seal_sha256"]
                if gate == "holdout"
                else None
            ),
            "privacy_host_identity_sha256": source.get("host_identity_sha256"),
            "pilot_protocol_sha256": source.get("protocol_sha256"),
        }
        if gate == "bilingual_review":
            reviewer = json.loads(
                (directory / source["reviewer_source_path"]).read_text(encoding="utf-8")
            )
            bindings["target_config_sha256"] = reviewer["config_sha256"]
        return release_evidence.verify_external_source(
            gate,
            source,
            candidate_commit=CANDIDATE,
            frozen_at=FREEZE,
            source_root=directory.resolve(),
            policy_bindings=bindings,
        )

    def test_holdout_privacy_and_pilot_metrics_are_derived(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            holdout_assertions, errors = self.verify(
                "holdout", self.holdout_source(directory), directory
            )
            self.assertEqual(errors, [])
            self.assertAlmostEqual(holdout_assertions["holdout_fraction"], 4 / 17)
            self.assertFalse(holdout_assertions["candidate_author_access"])
            privacy_assertions, errors = self.verify(
                "privacy_preflight", self.privacy_source(directory), directory
            )
            self.assertEqual(errors, [])
            self.assertEqual(privacy_assertions["unresolved_high_findings"], 0)
            pilot_assertions, errors = self.verify(
                "pilot", self.pilot_source(directory), directory
            )
            self.assertEqual(errors, [])
            self.assertEqual(pilot_assertions["episode_count"], 10)
            self.assertEqual(pilot_assertions["duration_days"], 28)

    def test_source_replay_rejects_omission_failure_and_fake_duration(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            holdout = self.holdout_source(directory)
            holdout["results"].pop()
            _, errors = self.verify("holdout", holdout, directory)
            self.assertTrue(any("exact sealed case set" in item for item in errors))
            holdout = self.holdout_source(directory)
            transcript_path = directory / json.loads(
                (directory / holdout["results"][0]["result_path"]).read_text(
                    encoding="utf-8"
                )
            )["transcript_path"]
            transcript_path.write_text("tampered transcript", encoding="utf-8")
            _, errors = self.verify("holdout", holdout, directory)
            self.assertTrue(any("transcript hash mismatch" in item for item in errors))
            holdout = self.holdout_source(directory)
            result_reference = holdout["results"][0]
            result_path = directory / result_reference["result_path"]
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["automated_status"] = "FAIL"
            result["hard_failure_codes"] = ["HOLDOUT_SAFETY_FAILURE"]
            result["result_sha256"] = release_evidence.object_hash(
                result, "result_sha256"
            )
            result_reference["result_sha256"] = result["result_sha256"]
            result_reference["result_file_sha256"] = write_json(result_path, result)
            _, errors = self.verify("holdout", holdout, directory)
            self.assertTrue(any("all_hard_gates_pass" in item for item in errors))
            holdout = self.holdout_source(directory)
            audit_path = directory / holdout["access_audit_path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            evidence_path, evidence_sha256 = write_evidence(
                directory, "candidate-author-access.evidence"
            )
            audit["events"].append(
                {
                    "event_id": "access-0000000000000001",
                    "actor_role": "candidate_author",
                    "accessed_at": "2026-08-14T00:00:00Z",
                    "evidence_path": evidence_path,
                    "evidence_sha256": evidence_sha256,
                }
            )
            audit["audit_sha256"] = release_evidence.object_hash(
                audit, "audit_sha256"
            )
            holdout["access_audit_sha256"] = audit["audit_sha256"]
            holdout["access_audit_file_sha256"] = write_json(audit_path, audit)
            _, errors = self.verify("holdout", holdout, directory)
            self.assertTrue(any("candidate-author access" in item for item in errors))
            holdout = self.holdout_source(directory)
            audit_path = directory / holdout["access_audit_path"]
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["events"] = [None]
            audit["audit_sha256"] = release_evidence.object_hash(
                audit, "audit_sha256"
            )
            holdout["access_audit_sha256"] = audit["audit_sha256"]
            holdout["access_audit_file_sha256"] = write_json(audit_path, audit)
            _, errors = self.verify("holdout", holdout, directory)
            self.assertTrue(any("external source replay failed" in item for item in errors))
            privacy = self.privacy_source(directory)
            privacy["checks"][0]["status"] = "FAIL"
            _, errors = self.verify("privacy_preflight", privacy, directory)
            self.assertTrue(any("storage_map_verified" in item for item in errors))
            privacy = self.privacy_source(directory)
            evidence_path, evidence_sha256 = write_evidence(
                directory, "privacy-extra-failed-control.evidence"
            )
            privacy["checks"].append(
                {
                    "check_id": "provider_retention",
                    "status": "FAIL",
                    "executed_at": "2026-08-13T00:00:00Z",
                    "evidence_path": evidence_path,
                    "evidence_sha256": evidence_sha256,
                }
            )
            _, errors = self.verify("privacy_preflight", privacy, directory)
            self.assertTrue(any("exact required control catalog" in item for item in errors))
            privacy = self.privacy_source(directory)
            privacy["named_host"] = "substituted-host"
            _, errors = self.verify("privacy_preflight", privacy, directory)
            self.assertTrue(any("differs from its identity" in item for item in errors))
            pilot = self.pilot_source(directory)
            pilot["ended_at"] = "2026-08-13T00:00:00Z"
            _, errors = self.verify("pilot", pilot, directory)
            self.assertTrue(any("exact episode coverage" in item for item in errors))
            pilot = self.pilot_source(directory)
            pilot["planned_episode_ids"][-1] = "episode-ffffffffffffffff"
            _, errors = self.verify("pilot", pilot, directory)
            self.assertTrue(any("owner-frozen protocol" in item for item in errors))
            pilot = self.pilot_source(directory)
            incident_path, incident_sha256 = write_evidence(
                directory, "pilot-critical-other.evidence"
            )
            pilot["incidents"].append(
                {
                    "incident_id": "CRITICAL_OTHER_INCIDENT",
                    "category": "other",
                    "severity": "critical",
                    "detected_at": "2026-08-20T00:00:00Z",
                    "evidence_path": incident_path,
                    "evidence_sha256": incident_sha256,
                }
            )
            _, errors = self.verify("pilot", pilot, directory)
            self.assertTrue(any("high-severity uncategorized" in item for item in errors))

    def test_reviewer_and_bilingual_sources_reconcile_exact_results(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            reviewer_source, results, manifest_entries = self.reviewer_fixture(directory)
            with mock.patch.object(
                release_evidence.campaign,
                "load_manifest_results",
                return_value=results,
            ):
                reviewer_assertions, errors = self.verify(
                    "reviewer_attestation", reviewer_source, directory
                )
                self.assertEqual(errors, [])
                self.assertEqual(reviewer_assertions["reviewer_count"], 2)
                aliased = copy.deepcopy(reviewer_source)
                aliased["reviewers"][1]["identity_evidence_path"] = aliased[
                    "reviewers"
                ][0]["identity_evidence_path"]
                aliased["reviewers"][1]["identity_evidence_sha256"] = aliased[
                    "reviewers"
                ][0]["identity_evidence_sha256"]
                _, alias_errors = self.verify(
                    "reviewer_attestation", aliased, directory
                )
                self.assertTrue(
                    any("identity attestations must be unique" in item for item in alias_errors)
                )
                reviewer_path = directory / "reviewer-source.json"
                reviewer_hash = write_json(reviewer_path, reviewer_source)
                bilingual_reviews = []
                for result, manifest_entry in zip(results, manifest_entries, strict=True):
                    review = result["reviews"][0]
                    bilingual_reviews.append(
                        {
                            "review_id": review["review_sha256"],
                            "run_id": result["run"]["run_id"],
                            "system_id": result["run"]["system_id"],
                            "language": "zh",
                            "result_sha256": manifest_entry["sha256"],
                            "primary_1_reviewer_id": review["reviewers"][0]["reviewer_id"],
                            "primary_2_reviewer_id": review["reviewers"][1]["reviewer_id"],
                            "primary_1_scores": review["reviewers"][0]["scores"],
                            "primary_2_scores": review["reviewers"][1]["scores"],
                            "meaning_or_safety_failure_codes": [],
                        }
                    )
                bilingual = {
                    "schema_version": "1.0",
                    "evidence_class": "bilingual-review-source",
                    "candidate_commit": CANDIDATE,
                    "completed_at": "2026-08-16T00:00:00Z",
                    "reviewer_source_path": reviewer_path.name,
                    "reviewer_source_sha256": reviewer_hash,
                    "fluent_reviewer_ids": [
                        "reviewer-0000000000000001",
                        "reviewer-0000000000000002",
                    ],
                    "expected_review_ids": [item["review_id"] for item in bilingual_reviews],
                    "reviews": bilingual_reviews,
                }
                assertions, errors = self.verify("bilingual_review", bilingual, directory)
                self.assertEqual(errors, [])
                self.assertEqual(assertions["minimum_system_kappa"], 1.0)
                tampered = copy.deepcopy(bilingual)
                tampered["reviews"][0]["primary_2_scores"] = {
                    name: 4 for name in scores()
                }
                _, errors = self.verify("bilingual_review", tampered, directory)
                self.assertTrue(any("differs from verified result" in item for item in errors))

    def test_malformed_scalar_assertions_and_generic_pass_fail_closed(self):
        self.assertTrue(
            release_evidence.assertion_errors(
                "privacy_preflight",
                {
                    "storage_map_verified": True,
                    "encryption_verified": True,
                    "no_sync_verified": True,
                    "backup_restore_verified": True,
                    "correction_export_deletion_verified": True,
                    "bounded_retention_verified": True,
                    "incident_response_tested": True,
                    "unresolved_high_findings": False,
                    "named_host": "host",
                },
            )
        )
        self.assertTrue(
            release_evidence.assertion_errors(
                "bilingual_review",
                {
                    "human_review_complete": True,
                    "meaning_preserved": True,
                    "safety_language_preserved": True,
                    "meaning_or_safety_failures": 0,
                    "fluent_reviewer_count": 2,
                    "minimum_system_kappa": 999,
                },
            )
        )
        with self.assertRaises(release_evidence.ReleaseEvidenceError):
            release_packet.build_gate_artifact(
                gate="holdout",
                candidate_commit=CANDIDATE,
                status="PASS",
                assertions={
                    "sealed": True,
                    "independent_authors": True,
                    "all_hard_gates_pass": True,
                    "candidate_author_access": False,
                    "holdout_fraction": 0.2,
                    "case_count": True,
                },
                evidence_refs=[HASH],
                hard_failures=[],
                executed_at=FREEZE,
            )

    def test_trust_policy_builder_freezes_every_preregistered_source(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name).resolve()
            config = {
                "source_commit": CANDIDATE,
                "provider": {"host": "restricted-evaluation-host-1"},
            }
            config_path = directory / "target-config.json"
            config_sha256 = write_json(config_path, config)
            holdout = self.holdout_source(directory)
            seal_path = directory / holdout["seal_path"]
            privacy = self.privacy_source(directory)
            host_path = directory / privacy["host_identity_path"]
            pilot = self.pilot_source(directory)
            protocol_path = directory / pilot["protocol_path"]
            authorities = []
            for index, role in enumerate(release_evidence.GATE_BY_ROLE, start=1):
                private_key = directory / f"authority-{index}.private.pem"
                public_key = directory / f"authority-{index}.public.pem"
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
                authorities.append(
                    {
                        "key_id": f"authority-{index:02d}",
                        "role": role,
                        "public_key_path": public_key.name,
                    }
                )
            roster_path = directory / "authorities.json"
            write_json(roster_path, {"authorities": authorities})
            for private_key in directory.glob("*.private.pem"):
                private_key.unlink()
            output = directory / "trust-policy.json"
            plan = {
                "schema_version": "1.0",
                "evidence_class": "qualification-packet-plan",
                "status": "DRAFT",
                "candidate_commit": CANDIDATE,
                "initialized_at": "2026-08-12T00:00:00Z",
                "attempt_campaign_id": "campaign-release-0001",
                "named_host": "restricted-evaluation-host-1",
                "environment_id": "pgc-private-evaluation-001",
                "storage_root_sha256": release_evidence.filesystem_object_identity(directory),
                "paths": {
                    "target_config": config_path.name,
                    "holdout_seal": seal_path.name,
                    "privacy_host_identity": host_path.name,
                    "pilot_protocol": protocol_path.name,
                    "authority_roster": roster_path.name,
                    "trust_policy": output.name,
                },
            }
            plan["plan_sha256"] = release_evidence.digest(plan)
            plan_path = directory / release_packet.QUALIFICATION_PLAN_NAME
            write_json(plan_path, plan)
            for path in directory.rglob("*"):
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
            args = SimpleNamespace(
                packet_root=directory,
                config=config_path,
                holdout_seal=seal_path,
                privacy_host_identity=host_path,
                pilot_protocol=protocol_path,
                authorities=roster_path,
                attempt_campaign_id="campaign-release-0001",
                output=output,
            )
            with (
                mock.patch.object(release_packet, "_source_commit", return_value=CANDIDATE),
                mock.patch.object(
                    release_packet.target_session, "validate_target_config", return_value=[]
                ),
                mock.patch.object(
                    release_packet.campaign, "_require_full_suite_scope", return_value=None
                ) as full_scope,
                mock.patch.object(
                    release_packet,
                    "now",
                    return_value=datetime(2026, 8, 13, tzinfo=timezone.utc),
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(release_packet.command_policy(args), 0)
            full_scope.assert_called_once()
            self.assertEqual(full_scope.call_args.args[1], config)
            policy = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(release_evidence.schema_errors(policy, "policy"), [])
            self.assertEqual(
                policy["qualification_plan_sha256"], plan["plan_sha256"]
            )
            self.assertEqual(policy["target_config_sha256"], config_sha256)
            self.assertEqual(policy["holdout_seal_sha256"], holdout["seal_sha256"])
            self.assertEqual(
                policy["privacy_host_identity_sha256"],
                privacy["host_identity_sha256"],
            )
            self.assertEqual(policy["pilot_protocol_sha256"], pilot["protocol_sha256"])
            self.assertEqual(len(policy["authorities"]), 9)

            leaked_private_key = directory / "leaked.private.pem"
            leaked_private_key.write_text(
                "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"
            )
            os.chmod(leaked_private_key, 0o600)
            with self.assertRaisesRegex(
                release_evidence.ReleaseEvidenceError, "private-key material"
            ):
                release_packet.prepare_trust_policy(
                    packet_root=directory,
                    config_path=config_path,
                    holdout_seal_path=seal_path,
                    privacy_host_identity_path=host_path,
                    pilot_protocol_path=protocol_path,
                    authorities_path=roster_path,
                    attempt_campaign_id="campaign-release-0001",
                    candidate=CANDIDATE,
                    frozen=datetime(2026, 8, 13, tzinfo=timezone.utc),
                )
            leaked_private_key.unlink()

            host_record = json.loads(host_path.read_text(encoding="utf-8"))
            aliased_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            aliased_protocol["witness_public_key_path"] = host_record[
                "audit_public_key_path"
            ]
            aliased_protocol["witness_public_key_sha256"] = host_record[
                "audit_public_key_sha256"
            ]
            aliased_protocol_path = directory / "aliased-pilot-protocol.json"
            write_json(aliased_protocol_path, aliased_protocol)
            os.chmod(aliased_protocol_path, 0o600)
            aliased_plan = copy.deepcopy(plan)
            aliased_plan["paths"]["pilot_protocol"] = aliased_protocol_path.name
            aliased_plan["plan_sha256"] = release_evidence.object_hash(
                aliased_plan, "plan_sha256"
            )
            plan_path.write_bytes(release_evidence.canonical_bytes(aliased_plan))
            os.chmod(plan_path, 0o600)
            with (
                mock.patch.object(
                    release_packet.target_session, "validate_target_config", return_value=[]
                ),
                mock.patch.object(
                    release_packet.campaign, "_require_full_suite_scope", return_value=None
                ),
                mock.patch.object(
                    release_packet,
                    "now",
                    return_value=datetime(2026, 8, 13, tzinfo=timezone.utc),
                ),
            ):
                with self.assertRaisesRegex(
                    release_evidence.ReleaseEvidenceError, "distinct key material"
                ):
                    release_packet.prepare_trust_policy(
                        packet_root=directory,
                        config_path=config_path,
                        holdout_seal_path=seal_path,
                        privacy_host_identity_path=host_path,
                        pilot_protocol_path=aliased_protocol_path,
                        authorities_path=roster_path,
                        attempt_campaign_id="campaign-release-0001",
                        candidate=CANDIDATE,
                        frozen=datetime(2026, 8, 13, tzinfo=timezone.utc),
                    )

if __name__ == "__main__":
    unittest.main()
