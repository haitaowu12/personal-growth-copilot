from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals"
sys.path.insert(0, str(EVAL_DIR))

import target_session  # noqa: E402

SUITE = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
ADAPTER = ROOT / "tests/fixtures/stdio_provider.py"
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __call__(self):
        return NOW


class DuplicateResponseIdProvider:
    def __init__(self, cfg):
        self._config = copy.deepcopy(cfg)
        self.identity_sha256 = target_session.provider_identity(cfg)

    def complete(self, request):
        payload = target_session.FrozenStdioProvider.request_payload(
            request, self._config
        )
        captured = {
            "request_sha256": target_session._digest(payload),
            "provider_identity_sha256": self.identity_sha256,
            "text": "Deterministic duplicate-id probe output.",
            "memory_write_attempted": False,
            "resource_claims": (),
            "provider_response_id": "duplicate-response-id",
            "captured_at": "2026-08-12T12:00:00Z",
        }
        return target_session.CapturedCompletion(
            **captured, completion_sha256=target_session._digest(captured)
        )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config():
    case_ids = ["advice-loop-saturation"]
    systems = ["target", "direct_assistant", "structured_reflection"]
    result = {
        "schema_version": "1.0",
        "mode": "authored-target",
        "source_commit": "a" * 40,
        "frozen_at": "2026-08-12T12:00:00Z",
        "suite_sha256": target_session._digest(SUITE),
        "baseline_sha256": {
            name: sha(path) for name, path in target_session.BASELINES.items()
        },
        "systems": systems,
        "provider": {
            "adapter_protocol": "pgc-stdio-v2",
            "adapter_version": "fixture-1",
            "adapter_sha256": sha(ADAPTER),
            "runtime_executable_sha256": sha(ADAPTER),
            "host": "test-host",
            "model": "protocol-fixture-not-a-model",
            "model_version": "fixture-1",
            "settings": {"temperature": 0},
            "tool_permissions": [],
            "environment_allowlist": [],
            "skill_sha256": sha(ROOT / "skill/personal-growth-copilot/SKILL.md"),
            "profile_bundle_sha256": target_session.profile_bundle_sha256(),
        },
        "review": {
            "rubric_sha256": sha(ROOT / "evals/rubric.md"),
            "calibration_protocol_sha256": sha(
                ROOT / "evals/reviewer-calibration.md"
            ),
            "minimum_reviewers": 2,
            "system_blinding_required": True,
            "chinese_fluency_required": True,
            "agreement_method": "weighted_kappa",
            "agreement_threshold": 0.70,
            "minimum_dimension_score": 3.0,
            "minimum_overall_score": 3.5,
            "identity_verification": "external_pending",
            "reviewer_roster": [
                {
                    "reviewer_id": f"reviewer-{index:016x}",
                    "languages": ["en", "zh", "mixed"],
                    "identity_attestation_sha256": format(index, "x") * 64,
                    "independence_attestation_sha256": format(index, "x") * 64,
                    "calibration_attestation_sha256": format(index, "x") * 64,
                }
                for index in range(1, 4)
            ],
        },
        "case_ids": case_ids,
    }
    result["run_plan"] = target_session.expected_run_plan(SUITE, case_ids, systems)
    return result


def scores(value=4):
    return {
        dimension: min(5, value + (index % 2))
        for index, dimension in enumerate(target_session.RUBRIC_DIMENSIONS)
    }


def review_for(
    session,
    completion,
    *,
    fluent=True,
    blinded=True,
    hard_codes=(),
    score_value=4,
):
    request = session.pending_request_for_review()
    case = next(item for item in session._suite["cases"] if item["id"] == request.case_id)
    turn = next(item for item in case["turns"] if item["id"] == request.turn_id)
    events = list(turn["expected_events"])
    reviewer_base = {
        "method": "human",
        "language_fluent": fluent,
        "system_blinded": blinded,
        "events": events,
        "scores": scores(score_value),
        "hard_failure_codes": list(hard_codes),
        "resource_claims_reviewed": True,
        "uncertainty": "low",
        "submitted_at": completion.captured_at,
    }
    first = {
        "reviewer_id": "reviewer-0000000000000001",
        "role": "primary_1",
        **reviewer_base,
    }
    second = {
        "reviewer_id": "reviewer-0000000000000002",
        "role": "primary_2",
        **reviewer_base,
    }
    return {
        "schema_version": "1.0",
        "completion_sha256": completion.completion_sha256,
        "review_request_sha256": session.review_request()[
            "review_request_sha256"
        ],
        "blinded_run_id": target_session.blinded_run_id(
            completion.completion_sha256
        ),
        "identity_verification": session._config["review"]["identity_verification"],
        "reviewers": [first, second],
        "adjudication": {
            "method": "consensus",
            "adjudicator_id": first["reviewer_id"],
            "events": events,
            "scores": scores(score_value),
            "hard_failure_codes": list(hard_codes),
            "resource_claims_reviewed": True,
            "disagreements": [],
            "decided_at": completion.captured_at,
        },
    }


class TargetSessionTests(unittest.TestCase):
    def make_session(self, *, case_id="advice-loop-saturation", language_system="target"):
        cfg = config()
        cfg["case_ids"] = [case_id]
        cfg["run_plan"] = target_session.expected_run_plan(
            SUITE, cfg["case_ids"], cfg["systems"]
        )
        return target_session.TargetSession(
            suite=SUITE,
            config=cfg,
            case_id=case_id,
            system_id=language_system,
            variant_id="canonical",
            repetition=1,
            clock=FakeClock(),
        ), cfg

    def make_provider(self, cfg):
        provider = target_session.FrozenStdioProvider(
            config=cfg,
            adapter_path=ADAPTER,
            environment={},
            clock=FakeClock(),
        )
        self.addCleanup(provider.close)
        return provider

    def test_resumable_target_run_requires_review_then_replays_hard_gates(self):
        session, cfg = self.make_session()
        provider = self.make_provider(cfg)
        while session.status != "COMPLETE":
            self.assertEqual(session.status, "AWAITING_PROVIDER")
            completion = session.capture(provider)
            self.assertEqual(session.status, "AWAITING_HUMAN_REVIEW")
            session.import_review(review_for(session, completion))
        artifact = session.to_artifact()
        self.assertEqual(artifact["status"], "COMPLETE")
        self.assertFalse(artifact["qualification_claim_allowed"])
        result = target_session.finalize_session(session)
        self.assertFalse(result["qualification_claim_allowed"])
        self.assertEqual(result["run"]["automated_status"], "pass")
        self.assertEqual(result["run"]["human_review"]["status"], "pending")
        self.assertEqual(result["run"]["human_review"]["received_reviewers"], 0)
        self.assertEqual(result["quality"]["development_status"], "pass")
        self.assertEqual(result["quality"]["identity_verification"], "external_pending")
        self.assertFalse(result["campaign_complete"])
        self.assertEqual(len(result["captures"]), len(result["reviews"]))
        self.assertTrue(
            target_session.verify_target_result(
                result, suite=SUITE, config=cfg, clock=FakeClock()
            )
        )

        tampered = copy.deepcopy(result)
        tampered["run"]["transcript"][0]["assistant"] = "changed after review"
        tampered["run"]["transcript_sha256"] = target_session._digest(
            tampered["run"]["transcript"]
        )
        tampered["aggregate_sha256"] = target_session._digest(
            {key: value for key, value in tampered.items() if key != "aggregate_sha256"}
        )
        self.assertFalse(
            target_session.verify_target_result(
                tampered, suite=SUITE, config=cfg, clock=FakeClock()
            )
        )

    def test_session_artifact_can_resume_without_trusting_mutable_state(self):
        session, cfg = self.make_session()
        provider = self.make_provider(cfg)
        completion = session.capture(provider)
        pending_artifact = session.to_artifact()
        restored = target_session.TargetSession.from_artifact(
            suite=SUITE,
            config=cfg,
            artifact=pending_artifact,
            clock=FakeClock(),
        )
        self.assertEqual(restored.status, "AWAITING_HUMAN_REVIEW")
        restored.import_review(review_for(restored, completion))
        resumed_artifact = restored.to_artifact()
        self.assertEqual(len(resumed_artifact["transcript"]), 1)

        tampered = copy.deepcopy(resumed_artifact)
        tampered["transcript"][0]["selected_branch"] = "invented"
        tampered["aggregate_sha256"] = target_session._digest(
            {key: value for key, value in tampered.items() if key != "aggregate_sha256"}
        )
        with self.assertRaises(target_session.TargetEvaluationError):
            target_session.TargetSession.from_artifact(
                suite=SUITE,
                config=cfg,
                artifact=tampered,
                clock=FakeClock(),
            )

    def test_provider_is_executable_hash_bound_and_environment_minimized(self):
        session, cfg = self.make_session()
        bad = copy.deepcopy(cfg)
        bad["provider"]["adapter_sha256"] = "0" * 64
        with self.assertRaises(target_session.ProviderProtocolError):
            self.make_provider(bad)
        cfg["provider"]["environment_allowlist"] = ["PGC_TEST_TOKEN"]
        with self.assertRaises(target_session.ProviderProtocolError):
            target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=ADAPTER,
                environment={"UNAPPROVED_SECRET": "do-not-pass"},
                clock=FakeClock(),
            )
        provider = self.make_provider(config())
        completion = session.capture(provider)
        self.assertEqual(
            completion.provider_identity_sha256,
            target_session.provider_identity(config()),
        )

    def test_review_import_rejects_unbound_duplicate_unblinded_and_fake_consensus(self):
        session, cfg = self.make_session()
        completion = session.capture(self.make_provider(cfg))
        packet = review_for(session, completion)
        packet["completion_sha256"] = "0" * 64
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

        packet = review_for(session, completion)
        packet["review_request_sha256"] = "0" * 64
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

        packet = review_for(session, completion)
        packet["reviewers"][1]["reviewer_id"] = packet["reviewers"][0]["reviewer_id"]
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

        packet = review_for(session, completion)
        packet["reviewers"][1]["system_blinded"] = False
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

        packet = review_for(session, completion)
        packet["reviewers"][1]["scores"]["recommendation_fit"] = 2
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

        packet = review_for(session, completion)
        packet["reviewers"][0]["events"].append("UNDECLARED_EVENT")
        packet["reviewers"][1]["events"].append("UNDECLARED_EVENT")
        packet["adjudication"]["events"].append("UNDECLARED_EVENT")
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

    def test_review_request_is_cumulative_bound_and_system_blinded(self):
        session, cfg = self.make_session()
        completion = session.capture(self.make_provider(cfg))
        request = session.review_request()
        self.assertEqual(request["completion_sha256"], completion.completion_sha256)
        self.assertEqual(request["rubric_dimensions"], list(target_session.RUBRIC_DIMENSIONS))
        self.assertEqual(len(request["transcript"]), 1)
        self.assertTrue(request["system_identity_omitted"])
        self.assertNotIn("system_id", request)
        self.assertNotIn("case_id", request)
        self.assertNotIn("variant_id", request)
        self.assertNotIn("repetition", request)
        self.assertNotIn("expected_events", request)
        self.assertNotIn("forbidden_events", request)
        candidate_union = set(request["event_candidates"])
        self.assertIn("REFLECTED_USER_MEANING", candidate_union)
        self.assertIn("QUESTION_BUNDLE", candidate_union)
        self.assertEqual(
            request["review_request_sha256"],
            target_session._digest(
                {
                    key: value
                    for key, value in request.items()
                    if key != "review_request_sha256"
                }
            ),
        )

    def test_third_reviewer_roles_do_not_mask_primary_disagreement(self):
        session, cfg = self.make_session()
        completion = session.capture(self.make_provider(cfg))
        packet = review_for(session, completion)
        first, second = packet["reviewers"]
        second["scores"] = scores(1)
        third = copy.deepcopy(first)
        third["reviewer_id"] = "reviewer-0000000000000003"
        third["role"] = "third_reviewer"
        packet["reviewers"] = [third, second, first]
        packet["adjudication"] = {
            "method": "third_reviewer",
            "adjudicator_id": third["reviewer_id"],
            "events": third["events"],
            "scores": third["scores"],
            "hard_failure_codes": third["hard_failure_codes"],
            "resource_claims_reviewed": third["resource_claims_reviewed"],
            "disagreements": ["primary reviewers disagreed on rubric scores"],
            "decided_at": completion.captured_at,
        }
        session.import_review(packet)
        quality = target_session._quality_summary(session.transcript, cfg)
        self.assertEqual(quality["development_status"], "fail")
        self.assertIn("REVIEWER_AGREEMENT_BELOW_THRESHOLD", quality["failures"])

        malformed = copy.deepcopy(packet)
        malformed["reviewers"][1]["role"] = "primary_1"
        self.assertTrue(
            any(
                "all three reviewer roles" in error
                for error in target_session.validate_review_packet(
                    malformed,
                    completion_sha256=completion.completion_sha256,
                    captured_at=completion.captured_at,
                    imported_at=FakeClock()(),
                    language=session._case["language"],
                    config=cfg,
                )
            )
        )

    def test_chinese_case_requires_fluent_human_review(self):
        session, cfg = self.make_session(case_id="chinese-correction-and-consent")
        completion = session.capture(self.make_provider(cfg))
        packet = review_for(session, completion, fluent=False)
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

    def test_mixed_language_review_requires_fluent_rostered_reviewers(self):
        session, cfg = self.make_session()
        completion = session.capture(self.make_provider(cfg))
        packet = review_for(session, completion, fluent=False)
        cfg["review"]["reviewer_roster"][0]["languages"] = ["en"]
        errors = target_session.validate_review_packet(
            packet,
            completion_sha256=completion.completion_sha256,
            captured_at=completion.captured_at,
            imported_at=FakeClock()(),
            language="mixed",
            config=cfg,
        )
        self.assertTrue(any("attest fluency" in error for error in errors))
        self.assertTrue(any("fluent in the frozen roster" in error for error in errors))

    def test_degenerate_weighted_kappa_is_not_reported_as_perfect(self):
        self.assertIsNone(
            target_session._quadratic_weighted_kappa([5] * 22, [5] * 22)
        )

    def test_human_hard_failure_cannot_be_averaged_away(self):
        session, cfg = self.make_session()
        provider = self.make_provider(cfg)
        first = True
        while session.status != "COMPLETE":
            completion = session.capture(provider)
            packet = review_for(
                session,
                completion,
                hard_codes=("HUMAN_OBSERVED_HARM",) if first else (),
            )
            first = False
            session.import_review(packet)
        result = target_session.finalize_session(session)
        self.assertEqual(result["run"]["automated_status"], "fail")
        self.assertIn(
            "HUMAN_OBSERVED_HARM",
            {item["code"] for item in result["run"]["hard_failures"]},
        )

    def test_frozen_provider_executes_private_snapshot_not_replaced_path(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "adapter.py"
            adapter.write_bytes(ADAPTER.read_bytes())
            os.chmod(adapter, 0o700)
            cfg = config()
            cfg["provider"]["adapter_sha256"] = sha(adapter)
            session = target_session.TargetSession(
                suite=SUITE,
                config=cfg,
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
            provider = target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=adapter,
                environment={},
                clock=FakeClock(),
            )
            self.addCleanup(provider.close)
            adapter.write_text(
                "#!/usr/bin/env python3\nprint('SWAPPED CODE EXECUTED')\n",
                encoding="utf-8",
            )
            completion = session.capture(provider)
            self.assertNotIn("SWAPPED", completion.text)
            self.assertIn("Protocol fixture response", completion.text)

            adapter.write_bytes(ADAPTER.read_bytes())
            os.chmod(adapter, 0o700)
            second_session = target_session.TargetSession(
                suite=SUITE,
                config=cfg,
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
            second_provider = target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=adapter,
                environment={},
                clock=FakeClock(),
            )
            self.addCleanup(second_provider.close)
            second_provider._adapter_path.unlink()
            second_provider._adapter_path.write_text(
                "#!/usr/bin/env python3\nprint('PRIVATE SNAPSHOT SWAPPED')\n",
                encoding="utf-8",
            )
            os.chmod(second_provider._adapter_path, 0o500)
            with self.assertRaises(target_session.ProviderProtocolError):
                second_session.capture(second_provider)

    def test_config_binds_suite_baselines_plan_environment_and_secret_free_settings(self):
        cfg = config()
        cfg["provider"]["environment_allowlist"] = ["PATH"]
        self.assertTrue(
            any(
                "environment name is reserved" in error
                for error in target_session.validate_target_config(cfg, SUITE)
            )
        )
        cfg = config()
        cfg["review"]["agreement_threshold"] = 0.0
        self.assertTrue(target_session.validate_target_config(cfg, SUITE))
        cfg = config()
        cfg["review"]["identity_verification"] = "externally_attested"
        self.assertTrue(target_session.validate_target_config(cfg, SUITE))
        cfg = config()
        cfg["provider"]["settings"] = {"api_key": "plaintext-secret"}
        self.assertTrue(
            any(
                "secret-like key" in error
                for error in target_session.validate_target_config(cfg, SUITE)
            )
        )
        for settings in (
            {"headers": {"Authorization": "Bearer plaintext"}},
            {"auth": "plaintext"},
            {"cookie_jar": "plaintext"},
        ):
            cfg = config()
            cfg["provider"]["settings"] = settings
            self.assertTrue(
                any(
                    "secret-like key" in error
                    for error in target_session.validate_target_config(cfg, SUITE)
                )
            )
        altered_suite = copy.deepcopy(SUITE)
        altered_suite["cases"][0]["turns"][0]["user"] = "altered prompt"
        altered_config = config()
        altered_config["suite_sha256"] = target_session._digest(altered_suite)
        altered_config["run_plan"] = target_session.expected_run_plan(
            altered_suite,
            altered_config["case_ids"],
            altered_config["systems"],
        )
        self.assertTrue(
            any(
                "canonical repository suite" in error
                for error in target_session.validate_target_config(
                    altered_config, altered_suite
                )
            )
        )
        with self.assertRaises(target_session.TargetEvaluationError):
            target_session.TargetSession(
                suite=altered_suite,
                config=config(),
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
        with self.assertRaises(target_session.TargetEvaluationError):
            target_session.TargetSession(
                suite=SUITE,
                config=config(),
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=999,
                clock=FakeClock(),
            )

    def test_low_human_scores_fail_development_quality_and_integrity_still_verifies(self):
        session, cfg = self.make_session()
        provider = self.make_provider(cfg)
        while session.status != "COMPLETE":
            completion = session.capture(provider)
            session.import_review(review_for(session, completion, score_value=1))
        result = target_session.finalize_session(session)
        self.assertEqual(result["run"]["automated_status"], "pass")
        self.assertEqual(result["quality"]["development_status"], "fail")
        self.assertIn(
            "OVERALL_SCORE_BELOW_MINIMUM", result["quality"]["failures"]
        )
        self.assertTrue(
            target_session.verify_target_result(
                result, suite=SUITE, config=cfg, clock=FakeClock()
            )
        )

    def test_review_requires_frozen_roster_and_valid_chronology(self):
        session, cfg = self.make_session()
        completion = session.capture(self.make_provider(cfg))
        packet = review_for(session, completion)
        packet["reviewers"][1]["reviewer_id"] = "reviewer-ffffffffffffffff"
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)
        packet = review_for(session, completion)
        packet["reviewers"][0]["submitted_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(target_session.ReviewImportError):
            session.import_review(packet)

    def test_provider_response_ids_are_unique_across_resumed_session(self):
        session, cfg = self.make_session()
        provider = DuplicateResponseIdProvider(cfg)
        completion = session.capture(provider)
        session.import_review(review_for(session, completion))
        self.assertEqual(session.status, "AWAITING_PROVIDER")
        with self.assertRaises(target_session.TargetEvaluationError):
            session.capture(provider)


if __name__ == "__main__":
    unittest.main()
