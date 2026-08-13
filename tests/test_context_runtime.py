from __future__ import annotations

import copy
import json
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import context_runtime  # noqa: E402
import growth_record  # noqa: E402

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self):
        self.current = NOW

    def __call__(self):
        return self.current


class FakeVerifier:
    def __init__(self):
        self.allowed: set[str] = set()

    def issue(self, scope: str, suffix: str = "1"):
        attestation_id = "att_" + suffix.zfill(32)
        self.allowed.add(attestation_id)
        return context_runtime.InquiryConsentAttestation(
            attestation_id=attestation_id,
            scope=scope,
            confirmed_at="2026-08-12T12:00:00Z",
        )

    def verify(self, attestation):
        if attestation.attestation_id not in self.allowed:
            return False
        self.allowed.remove(attestation.attestation_id)
        return True


class FakeModelDeltaVerifier:
    def __init__(self):
        self.allowed: set[str] = set()

    def issue(
        self,
        question_id: str,
        *,
        changed_fields: tuple[str, ...] = ("experiment",),
        suffix: str = "d1",
    ):
        attestation_id = "att_" + suffix.zfill(32)
        self.allowed.add(attestation_id)
        return context_runtime.ModelDeltaAttestation(
            attestation_id=attestation_id,
            question_id=question_id,
            changed_fields=changed_fields,
            previous_model_sha256="a" * 64,
            updated_model_sha256="b" * 64,
            observed_at="2026-08-12T12:00:00Z",
        )

    def verify(self, attestation):
        if attestation.attestation_id not in self.allowed:
            return False
        self.allowed.remove(attestation.attestation_id)
        return True


class FakeQuestionClassificationVerifier:
    def __init__(self):
        self.allowed: set[str] = set()
        self.counter = 0

    def issue(
        self,
        material_question,
        *,
        sensitivity: str = "ordinary",
        consent_scope: str | None = None,
        materiality_verified: bool = True,
    ):
        self.counter += 1
        attestation_id = "att_" + format(self.counter, "x").zfill(32)
        self.allowed.add(attestation_id)
        return context_runtime.QuestionClassificationAttestation(
            attestation_id=attestation_id,
            question_sha256=context_runtime._question_sha256(material_question),
            sensitivity=sensitivity,
            materiality_verified=materiality_verified,
            consent_scope_sha256=context_runtime._scope_sha256(consent_scope),
            classified_at="2026-08-12T12:00:00Z",
        )

    def verify(self, attestation):
        if attestation.attestation_id not in self.allowed:
            return False
        self.allowed.remove(attestation.attestation_id)
        return True


class FakeActionVerifier:
    def __init__(self):
        self.allowed: set[str] = set()

    def issue(
        self,
        action: str,
        payload: dict[str, object],
        *,
        suffix: str,
    ):
        attestation_id = "att_" + suffix.zfill(32)
        self.allowed.add(attestation_id)
        return context_runtime.HostUserActionAttestation(
            attestation_id=attestation_id,
            action=action,
            payload_sha256=context_runtime._action_payload_sha256(action, payload),
            confirmed_at="2026-08-12T12:00:00Z",
        )

    def verify(self, attestation):
        if attestation.attestation_id not in self.allowed:
            return False
        self.allowed.remove(attestation.attestation_id)
        return True


class SlowPermissiveActionVerifier:
    def verify(self, attestation):
        time.sleep(0.02)
        return True


def question(identifier: str, *, sensitive: bool = False, offers_skip: bool = False):
    return context_runtime.MaterialQuestion(
        question_id=identifier,
        text="What part of this situation would change the next step?",
        rationale="This distinguishes two different experiments.",
        would_change=("experiment", "hypothesis"),
        offers_skip=offers_skip,
    )


class ContextRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.verifier = FakeVerifier()
        self.classification_verifier = FakeQuestionClassificationVerifier()
        self.delta_verifier = FakeModelDeltaVerifier()
        self.action_verifier = FakeActionVerifier()
        self.action_gate = context_runtime.UserActionGate(self.action_verifier)
        self.session = context_runtime.ContextSession(
            consent_verifier=self.verifier,
            question_classification_verifier=self.classification_verifier,
            model_delta_verifier=self.delta_verifier,
            clock=self.clock,
        )

    def propose(
        self,
        material_question,
        *,
        sensitive: bool = False,
        consent_scope: str | None = None,
    ):
        return self.session.propose_question(
            material_question,
            classification=self.classification_verifier.issue(
                material_question,
                sensitivity="sensitive" if sensitive else "ordinary",
                consent_scope=consent_scope,
            ),
        )

    def test_sensitive_inquiry_requires_verified_bounded_consent_and_skip(self):
        decision = self.propose(
            question("q1", sensitive=True, offers_skip=True), sensitive=True
        )
        self.assertEqual(decision.status, "CONSENT_REQUIRED")
        with self.assertRaises(context_runtime.ConsentError):
            self.session.grant_inquiry_consent(
                context_runtime.InquiryConsentAttestation(
                    "att_ffffffffffffffffffffffffffffffff",
                    "history relevant to the current decision",
                    "2026-08-12T12:00:00Z",
                )
            )
        attestation = self.verifier.issue("history relevant to the current decision")
        self.session.grant_inquiry_consent(attestation)
        self.assertEqual(
            self.propose(
                question("q2", sensitive=True, offers_skip=False),
                sensitive=True,
                consent_scope=attestation.scope,
            ).status,
            "REJECTED",
        )
        self.assertEqual(
            self.propose(
                question("q3", sensitive=True, offers_skip=True),
                sensitive=True,
                consent_scope="unrelated personal history",
            ).status,
            "CONSENT_REQUIRED",
        )
        self.assertEqual(
            self.propose(
                question("q4", sensitive=True, offers_skip=True),
                sensitive=True,
                consent_scope=attestation.scope,
            ).status,
            "ALLOWED",
        )
        self.assertNotIn(attestation.scope, repr(self.session.history))
        self.session.revoke_inquiry_consent()
        self.assertFalse(self.session.inquiry_consent_active)
        self.assertIsNone(self.session.open_question_id)

    def test_question_materiality_one_at_a_time_and_saturation(self):
        immaterial = context_runtime.MaterialQuestion(
            question_id="q0",
            text="What else?",
            rationale="I am curious.",
            would_change=(),
        )
        self.assertEqual(self.propose(immaterial).status, "REJECTED")
        material = question("q-unverified")
        self.assertEqual(
            self.session.propose_question(
                material,
                classification=self.classification_verifier.issue(
                    material, materiality_verified=False
                ),
            ).status,
            "REJECTED",
        )
        self.assertEqual(self.propose(question("q1")).status, "ALLOWED")
        with self.assertRaises(context_runtime.QuestionError):
            self.propose(question("q2"))
        self.assertEqual(
            self.session.resolve_question("q1", model_delta=None),
            "MAY_ASK_NEXT_MATERIAL_QUESTION",
        )
        self.assertEqual(self.propose(question("q2")).status, "ALLOWED")
        self.assertEqual(
            self.session.resolve_question("q2", model_delta=None),
            "SUMMARIZE_AND_OFFER_ACTION",
        )
        self.assertTrue(self.session.saturated)
        self.assertEqual(self.propose(question("q3")).status, "SATURATED")

    def test_model_change_requires_a_host_verified_question_bound_delta(self):
        self.assertEqual(self.propose(question("q1")).status, "ALLOWED")
        wrong_field = self.delta_verifier.issue(
            "q1", changed_fields=("recommendation",), suffix="d2"
        )
        with self.assertRaises(context_runtime.QuestionError):
            self.session.resolve_question("q1", model_delta=wrong_field)
        valid = self.delta_verifier.issue("q1", suffix="d3")
        self.assertEqual(
            self.session.resolve_question("q1", model_delta=valid),
            "MAY_ASK_NEXT_MATERIAL_QUESTION",
        )
        self.assertIn("fields=experiment", self.session.history[-1].detail)

    def test_deep_context_requires_bounded_consent_even_for_ordinary_questions(self):
        deep_session = context_runtime.ContextSession(
            consent_verifier=self.verifier,
            question_classification_verifier=self.classification_verifier,
            model_delta_verifier=self.delta_verifier,
            clock=self.clock,
            mode="DEEP_CONTEXT",
        )
        material_question = question("deep-q", offers_skip=True)
        classification = self.classification_verifier.issue(material_question)
        self.assertEqual(
            deep_session.propose_question(
                material_question, classification=classification
            ).status,
            "CONSENT_REQUIRED",
        )
        consent = self.verifier.issue("extended inquiry about the current decision", "e1")
        deep_session.grant_inquiry_consent(consent)
        classification = self.classification_verifier.issue(
            material_question, consent_scope=consent.scope
        )
        self.assertEqual(
            deep_session.propose_question(
                material_question, classification=classification
            ).status,
            "ALLOWED",
        )
        deep_session.revoke_inquiry_consent()
        self.assertIsNone(deep_session.open_question_id)
        with self.assertRaises(AttributeError):
            deep_session.inquiry_scope = "caller-forged scope"

    def test_scale_is_user_defined_contextual_and_user_entered(self):
        scale_payload = {
            "scale_id": "scale-1",
            "construct": "Confidence in tomorrow's five-minute start",
            "minimum": 0.0,
            "maximum": 10.0,
            "low_anchor": "I do not expect to start",
            "high_anchor": "I expect to complete the five-minute start",
            "purpose": "Choose experiment size",
            "decision_link": "Reduce the action below five",
            "context_boundary": "Tomorrow's selected writing task only",
            "created_at": "2026-08-12T12:00:00Z",
            "review_at": "2026-08-19T12:00:00Z",
        }
        with self.assertRaises(context_runtime.ScaleError):
            context_runtime.define_scale(
                scale_id="scale-1",
                construct=scale_payload["construct"],
                minimum=0,
                maximum=10,
                low_anchor=scale_payload["low_anchor"],
                high_anchor=scale_payload["high_anchor"],
                purpose="Choose experiment size",
                decision_link="Reduce the action below five",
                context_boundary=scale_payload["context_boundary"],
                created_at=NOW,
                review_at=NOW + timedelta(days=7),
                attestation=context_runtime.HostUserActionAttestation(
                    "att_ffffffffffffffffffffffffffffffff",
                    "DEFINE_SCALE",
                    context_runtime._action_payload_sha256("DEFINE_SCALE", scale_payload),
                    "2026-08-12T12:00:00Z",
                ),
                user_action_gate=self.action_gate,
            )
        scale_attestation = self.action_verifier.issue(
            "DEFINE_SCALE", scale_payload, suffix="a1"
        )
        scale = context_runtime.define_scale(
            scale_id="scale-1",
            construct=scale_payload["construct"],
            minimum=0,
            maximum=10,
            low_anchor=scale_payload["low_anchor"],
            high_anchor=scale_payload["high_anchor"],
            purpose="Choose experiment size",
            decision_link="Reduce the action below five",
            context_boundary=scale_payload["context_boundary"],
            created_at=NOW,
            review_at=NOW + timedelta(days=7),
            attestation=scale_attestation,
            user_action_gate=self.action_gate,
        )
        wrong_checkin_payload = {
            "checkin_id": "checkin-1",
            "scale_id": "scale-1",
            "value": 8.0,
            "recorded_at": "2026-08-12T12:00:00Z",
            "context": "Before trying",
            "decision_link": "Reduce the action below five",
        }
        with self.assertRaises(context_runtime.ScaleError):
            context_runtime.record_check_in(
                scale=scale,
                checkin_id="checkin-1",
                value=7,
                recorded_at=NOW,
                context="Before trying",
                decision_link="Reduce the action below five",
                attestation=self.action_verifier.issue(
                    "ENTER_SCORE", wrong_checkin_payload, suffix="a2"
                ),
                user_action_gate=self.action_gate,
            )
        checkin_payload = {**wrong_checkin_payload, "value": 7.0}
        checkin = context_runtime.record_check_in(
            scale=scale,
            checkin_id="checkin-1",
            value=7,
            recorded_at=NOW,
            context="Before trying",
            decision_link="Reduce the action below five",
            attestation=self.action_verifier.issue(
                "ENTER_SCORE", checkin_payload, suffix="a3"
            ),
            user_action_gate=self.action_gate,
        )
        self.assertTrue(checkin.user_supplied)
        unrelated_payload = {**checkin_payload, "decision_link": "Infer personality"}
        with self.assertRaises(context_runtime.ScaleError):
            context_runtime.record_check_in(
                scale=scale,
                checkin_id="checkin-1",
                value=7,
                recorded_at=NOW,
                context="Before trying",
                decision_link="Infer personality",
                attestation=self.action_verifier.issue(
                    "ENTER_SCORE", unrelated_payload, suffix="a5"
                ),
                user_action_gate=self.action_gate,
            )
        paused = context_runtime.pause_scale_for_fixation(scale)
        with self.assertRaises(context_runtime.ScaleError):
            context_runtime.record_check_in(
                scale=paused,
                checkin_id="checkin-2",
                value=8,
                recorded_at=NOW + timedelta(days=1),
                context="Optimizing the number",
                decision_link="Reduce the action below five",
                attestation=self.action_verifier.issue(
                    "ENTER_SCORE",
                    {
                        **checkin_payload,
                        "checkin_id": "checkin-2",
                        "value": 8.0,
                        "recorded_at": "2026-08-13T12:00:00Z",
                        "context": "Optimizing the number",
                    },
                    suffix="a4",
                ),
                user_action_gate=self.action_gate,
            )

    def test_personal_decision_requires_real_options_and_user_choice(self):
        options = (
            context_runtime.DecisionOption(
                "a", "Try five minutes", "Informative", "Preparation", "high"
            ),
            context_runtime.DecisionOption(
                "b", "Schedule only", "Simple", "Less informative", "high"
            ),
        )
        choice_payload = {
            "decision_id": "decision-1",
            "question": "Which experiment?",
            "options": [
                {
                    "option_id": option.option_id,
                    "label": option.label,
                    "benefit": option.benefit,
                    "cost": option.cost,
                    "reversibility": option.reversibility,
                }
                for option in options
            ],
            "selected_option_id": "b",
            "created_at": "2026-08-12T12:00:00Z",
        }
        with self.assertRaises(context_runtime.DecisionError):
            context_runtime.record_user_decision(
                decision_id="decision-1",
                question="Which experiment?",
                options=options,
                selected_option_id="a",
                chosen_by="MODEL",
                rationale="Model preferred it",
                evidence_ids=(),
                assumptions=(),
                unknowns=(),
                created_at=NOW,
                attestation=self.action_verifier.issue(
                    "CHOOSE_OPTION", {**choice_payload, "selected_option_id": "a"}, suffix="b1"
                ),
                user_action_gate=self.action_gate,
            )

        with self.assertRaises(context_runtime.DecisionError):
            context_runtime.record_user_decision(
                decision_id="decision-1",
                question="Which experiment?",
                options=options,
                selected_option_id="b",
                chosen_by="USER",
                rationale="The user wants the simpler start.",
                evidence_ids=(),
                assumptions=(),
                unknowns=(),
                created_at=NOW,
                review_at=None,
                attestation=self.action_verifier.issue(
                    "CHOOSE_OPTION", choice_payload, suffix="b4"
                ),
                user_action_gate=self.action_gate,
            )

        invalid_options = (
            context_runtime.DecisionOption("", "Blank id", "Benefit", "Cost", "high"),
            options[1],
        )
        with self.assertRaises(context_runtime.DecisionError):
            context_runtime.record_user_decision(
                decision_id="decision-2",
                question="Which experiment?",
                options=invalid_options,
                selected_option_id="b",
                chosen_by="USER",
                rationale="The user chose.",
                evidence_ids=(),
                assumptions=(),
                unknowns=(),
                created_at=NOW,
                review_at=NOW + timedelta(days=7),
                attestation=self.action_verifier.issue(
                    "CHOOSE_OPTION", choice_payload, suffix="b5"
                ),
                user_action_gate=self.action_gate,
            )

        with self.assertRaises(context_runtime.DecisionError):
            context_runtime.record_user_decision(
                decision_id="decision-1",
                question="Which experiment?",
                options=options,
                selected_option_id="b",
                chosen_by="USER",
                rationale="The user wants the simpler start.",
                evidence_ids=("evidence-1",),
                assumptions=(),
                unknowns=(),
                created_at=NOW,
                review_at=NOW + timedelta(days=7),
                attestation=self.action_verifier.issue(
                    "CHOOSE_OPTION", {**choice_payload, "selected_option_id": "a"}, suffix="b2"
                ),
                user_action_gate=self.action_gate,
            )

        decision_attestation = self.action_verifier.issue(
            "CHOOSE_OPTION", choice_payload, suffix="b3"
        )
        decision = context_runtime.record_user_decision(
            decision_id="decision-1",
            question="Which experiment?",
            options=options,
            selected_option_id="b",
            chosen_by="USER",
            rationale="The user wants the simpler start.",
            evidence_ids=("evidence-1", "evidence-1"),
            assumptions=("Scheduling is possible.",),
            unknowns=("Whether ambiguity remains.",),
            created_at=NOW,
            review_at=NOW + timedelta(days=7),
            recommended_option_id="a",
            attestation=decision_attestation,
            user_action_gate=self.action_gate,
        )
        self.assertEqual(decision.selected_option_id, "b")
        self.assertEqual(decision.evidence_ids, ("evidence-1",))
        with self.assertRaises(context_runtime.DecisionError):
            context_runtime.record_user_decision(
                decision_id="decision-1",
                question="Which experiment?",
                options=options,
                selected_option_id="b",
                chosen_by="USER",
                rationale="The user wants the simpler start.",
                evidence_ids=("evidence-1",),
                assumptions=(),
                unknowns=(),
                created_at=NOW,
                review_at=NOW + timedelta(days=7),
                attestation=decision_attestation,
                user_action_gate=self.action_gate,
            )

    def test_malformed_host_records_fail_with_domain_errors(self):
        session = context_runtime.ContextSession(
            consent_verifier=self.verifier,
            question_classification_verifier=self.classification_verifier,
            model_delta_verifier=self.delta_verifier,
            clock=lambda: NOW,
        )
        with self.assertRaises(context_runtime.ConsentError):
            session.grant_inquiry_consent(
                context_runtime.InquiryConsentAttestation(None, "scope", "bad")
            )
        malformed_question = context_runtime.MaterialQuestion(
            "q-malformed", None, "rationale", ("hypothesis",), False
        )
        malformed_classification = context_runtime.QuestionClassificationAttestation(
            "att_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0" * 64,
            "ordinary",
            True,
            None,
            "2026-08-12T12:00:00Z",
        )
        with self.assertRaises(context_runtime.QuestionError):
            session.propose_question(
                malformed_question, classification=malformed_classification
            )
        with self.assertRaises(context_runtime.ScaleError):
            context_runtime.define_scale(
                scale_id=None,
                construct="confidence",
                minimum=0,
                maximum=10,
                low_anchor="low",
                high_anchor="high",
                purpose="decision",
                decision_link="decision",
                context_boundary="today",
                created_at=NOW,
                review_at=NOW + timedelta(days=1),
                attestation=context_runtime.HostUserActionAttestation(
                    None, "DEFINE_SCALE", "0" * 64, "2026-08-12T12:00:00Z"
                ),
                user_action_gate=self.action_gate,
            )

    def test_user_action_attestation_consume_is_atomic(self):
        gate = context_runtime.UserActionGate(SlowPermissiveActionVerifier())
        payload = {"scale_id": "scale-atomic"}
        attestation = context_runtime.HostUserActionAttestation(
            "att_cccccccccccccccccccccccccccccccc",
            "DEFINE_SCALE",
            context_runtime._action_payload_sha256("DEFINE_SCALE", payload),
            "2026-08-12T12:00:00Z",
        )

        def consume():
            try:
                gate.require(
                    action="DEFINE_SCALE",
                    payload=payload,
                    attestation=attestation,
                    at=NOW,
                )
            except context_runtime.ConsentError:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: consume(), range(2)))
        self.assertEqual(sorted(outcomes), ["accepted", "rejected"])

    def test_context_attestation_state_transitions_are_atomic(self):
        verifier = SlowPermissiveActionVerifier()
        consent_session = context_runtime.ContextSession(
            consent_verifier=verifier,
            question_classification_verifier=verifier,
            model_delta_verifier=verifier,
            clock=self.clock,
        )
        consent = context_runtime.InquiryConsentAttestation(
            "att_11111111111111111111111111111111",
            "bounded current-decision inquiry",
            "2026-08-12T12:00:00Z",
        )

        def grant():
            try:
                consent_session.grant_inquiry_consent(consent)
            except context_runtime.ContextRuntimeError:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                sorted(pool.map(lambda _: grant(), range(2))),
                ["accepted", "rejected"],
            )

        question_session = context_runtime.ContextSession(
            consent_verifier=verifier,
            question_classification_verifier=verifier,
            model_delta_verifier=verifier,
            clock=self.clock,
        )
        material = question("atomic-q")
        classification = context_runtime.QuestionClassificationAttestation(
            "att_22222222222222222222222222222222",
            context_runtime._question_sha256(material),
            "ordinary",
            True,
            None,
            "2026-08-12T12:00:00Z",
        )

        def propose():
            try:
                result = question_session.propose_question(
                    material, classification=classification
                )
            except context_runtime.ContextRuntimeError:
                return "rejected"
            return "accepted" if result.status == "ALLOWED" else "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                sorted(pool.map(lambda _: propose(), range(2))),
                ["accepted", "rejected"],
            )

        delta = context_runtime.ModelDeltaAttestation(
            "att_33333333333333333333333333333333",
            "atomic-q",
            ("experiment",),
            "a" * 64,
            "b" * 64,
            "2026-08-12T12:00:00Z",
        )

        def resolve():
            try:
                question_session.resolve_question("atomic-q", model_delta=delta)
            except context_runtime.ContextRuntimeError:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                sorted(pool.map(lambda _: resolve(), range(2))),
                ["accepted", "rejected"],
            )

    def test_schema_semantics_enforce_temporal_scale_and_evidence_links(self):
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )
        inventory = growth_record.temporal_inventory(example, NOW)
        self.assertTrue(inventory)
        self.assertTrue(all(item["status"] == "CURRENT" for item in inventory))

        stale = copy.deepcopy(example)
        stale["preferences"][0]["review_at"] = "2026-08-11T12:00:00Z"
        status = growth_record.temporal_inventory(stale, NOW)
        preference = next(item for item in status if item["id"] == "pref-1")
        self.assertEqual(preference["status"], "REVIEW_DUE")

        invalid = copy.deepcopy(example)
        invalid["check_ins"][0]["value"] = 11
        self.assertTrue(
            any("outside scale bounds" in error for error in growth_record.validate_record(invalid))
        )
        invalid = copy.deepcopy(example)
        invalid["hypotheses"][0]["supporting_evidence_ids"] = ["missing"]
        self.assertTrue(
            any("unknown evidence" in error for error in growth_record.validate_record(invalid))
        )
        with self.assertRaises(ValueError):
            growth_record.temporal_status(example["preferences"][0], NOW.replace(tzinfo=None))

    def test_growth_record_rejects_nonfinite_cyclic_temporal_and_malformed_values_safely(self):
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )
        invalid = copy.deepcopy(example)
        invalid["scales"][0]["minimum"] = float("nan")
        self.assertTrue(
            any(
                "non-finite numbers" in error
                for error in growth_record.validate_record(invalid)
            )
        )

        invalid = copy.deepcopy(example)
        invalid["experiments"][0]["review_at"] = "2026-08-10T12:00:00Z"
        self.assertTrue(
            any(
                "must be after start_at" in error
                for error in growth_record.validate_record(invalid)
            )
        )
        inventory = growth_record.temporal_inventory(example, NOW)
        self.assertIn(
            ("experiments", "exp-1"),
            {(item["collection"], item["id"]) for item in inventory},
        )

        invalid = copy.deepcopy(example)
        second = copy.deepcopy(invalid["decisions"][0])
        invalid["decisions"][0]["supersedes_decision_id"] = "decision-2"
        second["id"] = "decision-2"
        second["supersedes_decision_id"] = "decision-1"
        invalid["decisions"].append(second)
        self.assertTrue(
            any(
                "supersession cycle" in error
                for error in growth_record.validate_record(invalid)
            )
        )

        invalid = copy.deepcopy(example)
        invalid["decisions"][0]["supersedes_decision_id"] = []
        invalid["hypotheses"][0]["supporting_evidence_ids"] = [{}]
        invalid["check_ins"][0]["scale_id"] = {}
        invalid["decisions"][0]["options"][0]["id"] = []
        self.assertTrue(growth_record.validate_record(invalid))
        for malformed_evidence in (None, 7):
            invalid = copy.deepcopy(example)
            invalid["evidence"] = malformed_evidence
            self.assertTrue(growth_record.validate_record(invalid))
        malformed_properties = (
            ("hypotheses", 0, "supporting_evidence_ids"),
            ("hypotheses", 0, "disconfirming_or_missing_evidence_ids"),
            ("hypotheses", 0, "alternative_hypothesis_ids"),
            ("decisions", 0, "options"),
            ("decisions", 0, "status"),
            ("decisions", 0, "evidence_ids"),
        )
        for collection, index, field in malformed_properties:
            for malformed in (None, 7):
                invalid = copy.deepcopy(example)
                invalid[collection][index][field] = malformed
                self.assertTrue(growth_record.validate_record(invalid))
        with self.assertRaisesRegex(ValueError, "requires a valid growth record"):
            growth_record.temporal_inventory({"preferences": [7]}, NOW)

    def test_schema_errors_do_not_echo_private_instance_values(self):
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )
        marker = "PRIVATE_MARKER_7bd94"
        example["evidence"][0]["statement"] = marker + ("x" * 1600)
        errors = growth_record.validate_record(example)
        self.assertTrue(errors)
        self.assertNotIn(marker, repr(errors))
        semantic = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )
        semantic["hypotheses"][0]["supporting_evidence_ids"] = [marker]
        semantic["decisions"][0]["selected_option_id"] = marker
        semantic["corrections"].append(
            {
                "id": "correction-private-probe",
                "target_id": marker,
                "replacement_or_action": "Remove the invalid reference.",
                "recorded_at": "2026-08-12T12:00:00Z",
            }
        )
        errors = growth_record.validate_record(semantic)
        self.assertTrue(errors)
        self.assertNotIn(marker, repr(errors))


if __name__ == "__main__":
    unittest.main()
