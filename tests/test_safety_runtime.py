from __future__ import annotations

import re
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skill/personal-growth-copilot/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import safety_runtime as safety  # noqa: E402
NOW = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


class Resolver:
    def __init__(self, resources=(), error: Exception | None = None):
        self.resources = resources
        self.error = error
        self.calls = []

    def resolve(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.resources


def resource(*, verified_delta=-60, expiry_delta=3600):
    return safety.VerifiedResource(
        name="Synthetic Current Service",
        channel="phone",
        contact="synthetic-contact",
        jurisdiction="Synthetic Jurisdiction",
        source_uri="https://example.test/current-resource",
        verified_at=(NOW + timedelta(seconds=verified_delta)).isoformat(),
        expires_at=(NOW + timedelta(seconds=expiry_delta)).isoformat(),
    )


class SafetyMachineTests(unittest.TestCase):
    def session(self):
        return safety.SafetySession(clock=lambda: NOW)

    def test_canonical_machine_is_complete(self):
        machine = safety.load_machine()
        self.assertEqual(safety.validate_machine_spec(machine), [])
        self.assertEqual(set(machine["states"]), safety.REQUIRED_STATES)
        self.assertTrue(safety.REQUIRED_EVENTS.issubset({
            item["event"] for item in machine["transitions"]
        }))

    def test_invalid_specs_fail_closed(self):
        machine = safety.load_machine()
        broken = deepcopy(machine)
        broken["states"]["ACUTE_DANGER"]["memory_write_allowed"] = True
        self.assertTrue(any("freeze memory" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        broken["transitions"].append(deepcopy(broken["transitions"][0]))
        self.assertTrue(any("duplicate" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        broken["states"]["ACUTE_DANGER"]["coaching_allowed"] = True
        self.assertTrue(any("stop ordinary coaching" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        acute_entry = next(
            item
            for item in broken["transitions"]
            if item["from"] == "ORDINARY_COACHING"
            and item["event"] == "ACUTE_DANGER_SIGNAL"
        )
        acute_entry["effects"].remove("freeze_memory")
        self.assertTrue(any("must freeze memory" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        repeated_signal = next(
            item
            for item in broken["transitions"]
            if item["from"] == "ACUTE_DANGER"
            and item["event"] == "ACUTE_DANGER_SIGNAL"
        )
        repeated_signal["effects"] = ["mark_support_connected"]
        self.assertTrue(any("only IMMEDIATE_SUPPORT_CONNECTED" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        broken["states"]["SIGNIFICANT_IMPAIRMENT"]["resource_requirement"] = "NONE"
        self.assertTrue(any("governed tuple" in error for error in safety.validate_machine_spec(broken)))
        broken = deepcopy(machine)
        broken["transitions"].append(
            {
                "id": "SAFE-TRANS-020",
                "from": "ACUTE_DANGER",
                "event": "SAFE_RETURN_CONFIRMED",
                "to": "ORDINARY_COACHING",
            }
        )
        self.assertTrue(any("transition table differs" in error for error in safety.validate_machine_spec(broken)))

    def test_acute_entry_freezes_memory_and_rejects_ordinary_coaching(self):
        session = self.session()
        result = session.transition("INDIRECT_ACUTE_RISK_SIGNAL")
        self.assertEqual(result.state_after, "ACUTE_DANGER")
        self.assertFalse(session.coaching_allowed)
        self.assertFalse(session.memory_write_allowed)
        self.assertTrue(session.memory_latched)
        with self.assertRaises(safety.RestrictedMemoryWrite):
            session.require_memory_write_allowed()
        with self.assertRaises(safety.InvalidTransition):
            session.transition("SAFE_RETURN_CONFIRMED")

    def test_validated_machine_is_isolated_from_caller_mutation(self):
        machine = safety.load_machine()
        session = safety.SafetySession(machine=machine, clock=lambda: NOW)
        machine["states"]["ACUTE_DANGER"]["coaching_allowed"] = True
        entry = next(
            item
            for item in machine["transitions"]
            if item["from"] == "ORDINARY_COACHING"
            and item["event"] == "ACUTE_DANGER_SIGNAL"
        )
        entry["to"] = "ORDINARY_COACHING"
        session.transition("ACUTE_DANGER_SIGNAL")
        self.assertEqual(session.state, "ACUTE_DANGER")
        self.assertFalse(session.coaching_allowed)

    def test_acute_exit_requires_connection_and_memory_stays_frozen(self):
        session = self.session()
        session.transition("ACUTE_DANGER_SIGNAL")
        with self.assertRaises(safety.SafetyGuardFailed):
            session.transition("IMMEDIATE_DANGER_REDUCED")
        session.transition("IMMEDIATE_SUPPORT_CONNECTED")
        session.transition("IMMEDIATE_DANGER_REDUCED")
        self.assertEqual(session.state, "POST_CRISIS_RETURN")
        self.assertFalse(session.memory_write_allowed)
        session.transition("SAFE_RETURN_CONFIRMED")
        self.assertEqual(session.state, "ORDINARY_COACHING")
        self.assertFalse(session.memory_write_allowed)
        session.transition("MEMORY_REENABLE_CONFIRMED")
        self.assertTrue(session.memory_write_allowed)

    def test_transition_failure_is_atomic_before_memory_reenable(self):
        session = self.session()
        session.transition("ACUTE_DANGER_SIGNAL")
        session.transition("IMMEDIATE_SUPPORT_CONNECTED")
        session.transition("IMMEDIATE_DANGER_REDUCED")
        session.transition("SAFE_RETURN_CONFIRMED")
        history_before = session.history
        with patch.object(session, "_clock", side_effect=RuntimeError("clock failed")):
            with self.assertRaises(RuntimeError):
                session.transition("MEMORY_REENABLE_CONFIRMED")
        self.assertTrue(session.memory_latched)
        self.assertFalse(session.memory_write_allowed)
        self.assertEqual(session.history, history_before)
        with patch("safety_runtime.secrets.token_hex", side_effect=RuntimeError("rng failed")):
            with self.assertRaises(RuntimeError):
                session.transition("MEMORY_REENABLE_CONFIRMED")
        self.assertTrue(session.memory_latched)
        self.assertFalse(session.memory_write_allowed)
        self.assertEqual(session.history, history_before)

    def test_all_declared_transitions_are_observable(self):
        machine = safety.load_machine()
        observed_rule_ids = set()
        for rule in machine["transitions"]:
            session = self.session()
            source = rule["from"]
            if source == "SCOPE_BOUNDARY":
                session.transition("OUT_OF_SCOPE_REQUEST")
            elif source == "SIGNIFICANT_IMPAIRMENT":
                session.transition("SIGNIFICANT_IMPAIRMENT_SIGNAL")
            elif source == "ACUTE_DANGER":
                session.transition("ACUTE_DANGER_SIGNAL")
            elif source == "POST_CRISIS_RETURN":
                session.transition("ACUTE_DANGER_SIGNAL")
                session.transition("IMMEDIATE_SUPPORT_CONNECTED")
                session.transition("IMMEDIATE_DANGER_REDUCED")
            elif rule["event"] == "MEMORY_REENABLE_CONFIRMED":
                session.transition("ACUTE_DANGER_SIGNAL")
                session.transition("IMMEDIATE_SUPPORT_CONNECTED")
                session.transition("IMMEDIATE_DANGER_REDUCED")
                session.transition("SAFE_RETURN_CONFIRMED")
            if rule["event"] == "IMMEDIATE_DANGER_REDUCED":
                session.transition("IMMEDIATE_SUPPORT_CONNECTED")
            transition = session.transition(rule["event"])
            observed_rule_ids.add(transition.rule_id)
            self.assertRegex(transition.audit_event_id, r"^safe-event-[0-9a-f]{32}$")
        self.assertEqual(observed_rule_ids, {item["id"] for item in machine["transitions"]})

    def test_resource_lookup_requires_acute_state(self):
        with self.assertRaises(safety.ResourceResolutionError):
            safety.resolve_current_resources(
                self.session(), Resolver(), location="Test", language="en", clock=lambda: NOW
            )

    def test_missing_location_uses_content_free_fallback_without_resolver(self):
        session = self.session()
        session.transition("ACUTE_DANGER_SIGNAL")
        resolver = Resolver()
        result = safety.resolve_current_resources(
            session, resolver, location=None, language="en", clock=lambda: NOW
        )
        self.assertEqual(result.status, "LOCATION_REQUIRED")
        self.assertFalse(result.resolver_attempted)
        self.assertEqual(resolver.calls, [])
        self.assertEqual(result.resources, ())
        self.assertFalse(any(re.search(r"\+?\d[\d -]{5,}", value) for value in result.fallback_actions))

    def test_resolver_exception_and_stale_result_fail_without_contact_claim(self):
        session = self.session()
        session.transition("ACUTE_DANGER_SIGNAL")
        failed = safety.resolve_current_resources(
            session,
            Resolver(error=RuntimeError("sensitive host detail")),
            location="Test",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(failed.status, "UNAVAILABLE")
        self.assertEqual(failed.failure_code, "HOST_RESOLVER_FAILED")
        self.assertNotIn("sensitive", repr(failed))
        stale = safety.resolve_current_resources(
            session,
            Resolver((resource(expiry_delta=-1),)),
            location="Test",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(stale.status, "UNAVAILABLE")
        self.assertEqual(stale.resources, ())
        wrong_jurisdiction = safety.resolve_current_resources(
            session,
            Resolver((resource(),)),
            location="Different Jurisdiction",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(wrong_jurisdiction.status, "UNAVAILABLE")
        self.assertEqual(wrong_jurisdiction.failure_code, "INVALID_OR_STALE_HOST_RESULT")
        malformed = safety.resolve_current_resources(
            session,
            Resolver(({"name": "not-a-verified-resource"},)),
            location="Test",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(malformed.status, "UNAVAILABLE")
        self.assertEqual(malformed.failure_code, "INVALID_OR_STALE_HOST_RESULT")
        bad_channel = safety.resolve_current_resources(
            session,
            Resolver((safety.VerifiedResource(
                name="Synthetic Current Service",
                channel=None,
                contact="synthetic-contact",
                jurisdiction="Test",
                source_uri="https://example.test/current-resource",
                verified_at=(NOW - timedelta(minutes=1)).isoformat(),
                expires_at=(NOW + timedelta(hours=1)).isoformat(),
            ),)),
            location="Test",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(bad_channel.status, "UNAVAILABLE")

    def test_only_exact_current_host_claims_are_renderable(self):
        session = self.session()
        session.transition("ACUTE_DANGER_SIGNAL")
        current = resource()
        result = safety.resolve_current_resources(
            session,
            Resolver((current,)),
            location="Synthetic Jurisdiction",
            language="en",
            clock=lambda: NOW,
        )
        self.assertEqual(result.status, "VERIFIED")
        exact = [{"name": current.name, "contact": current.contact, "source_uri": current.source_uri}]
        fabricated = [{"name": current.name, "contact": "other", "source_uri": current.source_uri}]
        self.assertTrue(safety.resource_claims_are_verified(result, exact))
        self.assertFalse(safety.resource_claims_are_verified(result, fabricated))


if __name__ == "__main__":
    unittest.main()
