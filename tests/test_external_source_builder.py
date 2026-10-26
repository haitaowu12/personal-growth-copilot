from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import external_source_builder as builder  # noqa: E402
import release_evidence  # noqa: E402
from tests import test_external_gate_sources as external_fixtures  # noqa: E402

CANDIDATE = external_fixtures.CANDIDATE
FREEZE = external_fixtures.FREEZE
sign_payload = external_fixtures.sign_payload
signing_key = external_fixtures.signing_key
write_evidence = external_fixtures.write_evidence
write_json = external_fixtures.write_json


def write_signature(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="utf-8")


class ExternalSourceBuilderTests(unittest.TestCase):
    def verify(self, gate: str, source: dict, directory: Path, **bindings):
        return release_evidence.verify_external_source(
            gate,
            source,
            candidate_commit=CANDIDATE,
            frozen_at=FREEZE,
            source_root=directory.resolve(),
            policy_bindings=bindings,
        )

    def test_privacy_builder_derives_hashes_and_requires_external_signature(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            private_key, public_name, _ = signing_key(directory, "privacy-builder")
            host_path = directory / "host.json"
            host = builder.privacy_host_identity(
                output=host_path,
                named_host="restricted-evaluation-host-1",
                environment_id="pgc-private-evaluation-001",
                storage_root=directory,
                audit_id="privacy-audit-0000000000000001",
                audit_public_key_path=directory / public_name,
                captured_at=FREEZE,
            )
            write_json(host_path, host)
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
                evidence_path, _ = write_evidence(
                    directory, f"{check_id}.evidence"
                )
                checks.append(
                    {
                        "check_id": check_id,
                        "status": "PASS",
                        "executed_at": "2026-08-13T00:00:00Z",
                        "evidence_path": evidence_path,
                    }
                )
            checks_path = directory / "checks.json"
            findings_path = directory / "findings.json"
            write_json(checks_path, {"checks": checks})
            write_json(findings_path, {"findings": []})
            request_path = directory / "privacy-request.json"
            request = builder.prepare_privacy_source(
                output=request_path,
                candidate_commit=CANDIDATE,
                host_identity_path=host_path,
                checks_path=checks_path,
                findings_path=findings_path,
                retention_days=30,
                completed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
                nonce="privacy-builder-nonce-0001",
            )
            write_json(request_path, request)
            signature = sign_payload(
                directory, "privacy-builder", request["payload"], private_key
            )
            signature_path = directory / "privacy.signature.base64"
            write_signature(signature_path, signature)
            source = builder.assemble_privacy_source(
                output=directory / "privacy-source.json",
                request_path=request_path,
                signature_path=signature_path,
            )
            assertions, errors = self.verify(
                "privacy_preflight",
                source,
                directory,
                privacy_host_identity_sha256=hashlib.sha256(
                    host_path.read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(errors, [])
            self.assertTrue(assertions["correction_export_deletion_verified"])
            self.assertTrue(assertions["bounded_retention_verified"])

            bad_signature = directory / "privacy-bad.signature.base64"
            write_signature(bad_signature, base64.b64encode(b"x" * 64).decode())
            with self.assertRaises(release_evidence.ReleaseEvidenceError):
                builder.assemble_privacy_source(
                    output=directory / "bad.json",
                    request_path=request_path,
                    signature_path=bad_signature,
                )

    def test_pilot_builder_derives_complete_ledger_and_verifies_signature(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            private_key, public_name, _ = signing_key(directory, "pilot-builder")
            episode_ids = [f"episode-{index:016x}" for index in range(1, 11)]
            protocol_path = directory / "pilot-protocol.json"
            protocol = builder.pilot_protocol(
                output=protocol_path,
                candidate_commit=CANDIDATE,
                preregistered_at=FREEZE,
                ledger_id="pilot-ledger-0000000000000001",
                witness_public_key_path=directory / public_name,
                planned_episode_ids=episode_ids,
            )
            write_json(protocol_path, protocol)
            start = datetime(2026, 8, 13, tzinfo=timezone.utc)
            episodes = []
            offsets = (0, 3, 6, 9, 12, 15, 18, 21, 24, 28)
            for index, episode_id in enumerate(episode_ids):
                consent_path, _ = write_evidence(
                    directory, f"consent-{index}.evidence"
                )
                episode_path, _ = write_evidence(
                    directory, f"episode-{index}.evidence"
                )
                scheduled = start + timedelta(days=offsets[index])
                episodes.append(
                    {
                        "episode_id": episode_id,
                        "scheduled_at": builder.timestamp(scheduled),
                        "closed_at": builder.timestamp(scheduled + timedelta(hours=1)),
                        "outcome": "COMPLETED",
                        "consent_evidence_path": consent_path,
                        "episode_evidence_path": episode_path,
                        "withdrawal_requested_at": None,
                        "withdrawal_honored_at": None,
                        "deletion_requested": False,
                        "deletion_completed_at": None,
                    }
                )
            episodes_path = directory / "episodes.json"
            incidents_path = directory / "incidents.json"
            write_json(episodes_path, {"episodes": episodes})
            write_json(incidents_path, {"incidents": []})
            request_path = directory / "pilot-request.json"
            request = builder.prepare_pilot_source(
                output=request_path,
                candidate_commit=CANDIDATE,
                protocol_path=protocol_path,
                episodes_path=episodes_path,
                incidents_path=incidents_path,
                started_at=start,
                ended_at=start + timedelta(days=28, hours=1),
                nonce="pilot-builder-nonce-0001",
            )
            write_json(request_path, request)
            signature = sign_payload(
                directory, "pilot-builder", request["payload"], private_key
            )
            signature_path = directory / "pilot.signature.base64"
            write_signature(signature_path, signature)
            source = builder.assemble_pilot_source(
                output=directory / "pilot-source.json",
                request_path=request_path,
                signature_path=signature_path,
            )
            assertions, errors = self.verify(
                "pilot",
                source,
                directory,
                pilot_protocol_sha256=hashlib.sha256(
                    protocol_path.read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(errors, [])
            self.assertEqual(assertions["episode_count"], 10)
            self.assertEqual(assertions["duration_days"], 28)

    def test_holdout_builder_replays_exact_chain(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            private_key, public_name, _ = signing_key(directory, "holdout-builder")
            ciphertext, _ = write_evidence(directory, "holdout.enc")
            case_schema, _ = write_evidence(directory, "holdout-schema.json")
            identity, _ = write_evidence(directory, "author-identity.evidence")
            independence, _ = write_evidence(
                directory, "author-independence.evidence"
            )
            authorship, _ = write_evidence(
                directory, "author-authorship.evidence"
            )
            authors_path = directory / "authors.json"
            write_json(
                authors_path,
                {
                    "authors": [
                        {
                            "author_id": "author-0000000000000001",
                            "subject_sha256": "1" * 64,
                            "identity_evidence_path": identity,
                            "independence_evidence_path": independence,
                            "authorship_evidence_path": authorship,
                            "independence_verified": True,
                        }
                    ]
                },
            )
            case_id = "holdout-builder-case"
            seal_path = directory / "seal.json"
            seal = builder.holdout_seal(
                output=seal_path,
                candidate_commit=CANDIDATE,
                sealed_at=FREEZE,
                public_case_count=3,
                sealed_case_ids=[case_id],
                ciphertext_path=directory / ciphertext,
                case_schema_path=directory / case_schema,
                witness_public_key_path=directory / public_name,
                authors_path=authors_path,
            )
            write_json(seal_path, seal)
            access_events = directory / "access-events.json"
            write_json(access_events, {"events": []})
            access_path = directory / "access.json"
            access = builder.holdout_access_audit(
                output=access_path,
                candidate_commit=CANDIDATE,
                seal_path=seal_path,
                events_path=access_events,
                generated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            )
            write_json(access_path, access)
            transcript = directory / "transcript.json"
            transcript.write_text('{"turns":[]}', encoding="utf-8")
            result_path = directory / "result.json"
            result = builder.holdout_result(
                output=result_path,
                candidate_commit=CANDIDATE,
                case_id=case_id,
                completed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                automated_status="PASS",
                hard_failure_codes=[],
                transcript_path=transcript,
            )
            write_json(result_path, result)
            event_path = directory / "attempt-events.json"
            write_json(
                event_path,
                {
                    "events": [
                        {
                            "attempt_id": "attempt-" + "1" * 32,
                            "occurred_at": "2026-08-15T00:00:00Z",
                            "outcome": "PASS",
                        }
                    ]
                },
            )
            request_path = directory / "attempt-request.json"
            request = builder.prepare_holdout_attempt(
                output=request_path,
                candidate_commit=CANDIDATE,
                case_id=case_id,
                result_path=result_path,
                events_path=event_path,
                seal_path=seal_path,
                issued_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                nonce="holdout-builder-nonce-0001",
            )
            write_json(request_path, request)
            signature = sign_payload(
                directory, "holdout-builder", request["payload"], private_key
            )
            signature_path = directory / "attempt.signature.base64"
            write_signature(signature_path, signature)
            attempt_path = directory / "attempt.json"
            attempt = builder.assemble_holdout_attempt(
                output=attempt_path,
                request_path=request_path,
                signature_path=signature_path,
            )
            write_json(attempt_path, attempt)
            source = builder.holdout_source(
                output=directory / "holdout-source.json",
                candidate_commit=CANDIDATE,
                seal_path=seal_path,
                access_audit_path=access_path,
                result_paths=[result_path],
                attempt_paths=[attempt_path],
                revealed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            )
            assertions, errors = self.verify(
                "holdout",
                source,
                directory,
                holdout_seal_sha256=seal["seal_sha256"],
            )
            self.assertEqual(errors, [])
            self.assertTrue(assertions["sealed"])
            self.assertTrue(assertions["all_hard_gates_pass"])

    def test_reviewer_and_bilingual_builders_derive_verified_results(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            fixture = external_fixtures.ExternalGateSourceTests()
            source_fixture, results, _ = fixture.reviewer_fixture(directory)
            declarations = {
                "reviewers": [
                    {
                        key: reviewer[key]
                        for key in (
                            "reviewer_id",
                            "languages",
                            "identity_evidence_path",
                            "independence_evidence_path",
                            "calibration_evidence_path",
                            "calibrated_at",
                            "identity_verified",
                            "independence_verified",
                            "calibration_passed",
                        )
                    }
                    for reviewer in source_fixture["reviewers"]
                ]
            }
            declarations_path = directory / "reviewer-declarations.json"
            write_json(declarations_path, declarations)
            config_path = directory / source_fixture["config_path"]
            manifest_path = directory / source_fixture["result_manifest_path"]
            calibration_path = directory / source_fixture["calibration_set_path"]
            output = directory / "reviewer-source.json"
            with (
                mock.patch.object(
                    builder.target_session, "validate_target_config", return_value=[]
                ),
                mock.patch.object(
                    builder.campaign, "load_manifest_results", return_value=results
                ),
            ):
                reviewer_source = builder.reviewer_source(
                    output=output,
                    config_path=config_path,
                    manifest_path=manifest_path,
                    calibration_set_path=calibration_path,
                    declarations_path=declarations_path,
                    completed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                )
            self.assertEqual(
                {item["used_run_count"] for item in reviewer_source["reviewers"]},
                {5},
            )
            write_json(output, reviewer_source)
            with mock.patch.object(
                builder.campaign, "load_manifest_results", return_value=results
            ):
                bilingual = builder.bilingual_source(
                    output=directory / "bilingual-source.json",
                    reviewer_source_path=output,
                    fluent_reviewer_ids=[
                        "reviewer-0000000000000001",
                        "reviewer-0000000000000002",
                    ],
                    completed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
                )
            self.assertEqual(len(bilingual["reviews"]), 5)
            self.assertEqual(
                set(bilingual["expected_review_ids"]),
                {item["review_id"] for item in bilingual["reviews"]},
            )


if __name__ == "__main__":
    unittest.main()
