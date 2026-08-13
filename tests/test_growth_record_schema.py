from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import growth_record  # noqa: E402


class GrowthRecordSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8")
        )

    def assert_schema_rejects(
        self, name: str, mutate: Callable[[dict[str, Any]], None]
    ) -> None:
        candidate = copy.deepcopy(self.example)
        mutate(candidate)
        with self.subTest(name=name):
            self.assertTrue(growth_record.validate_against_schema(candidate))
            self.assertTrue(growth_record.validate_record(candidate))

    def test_canonical_schema_is_the_runtime_authority(self) -> None:
        self.assertEqual(growth_record.validate_against_schema(self.example), [])
        self.assertEqual(growth_record.validate_record(self.example), [])
        self.assertTrue(growth_record.validate_against_schema([]))
        self.assertTrue(growth_record.validate_record([]))

    def test_every_declared_nested_rule_has_a_rejecting_mutation(self) -> None:
        schema = json.loads(growth_record.SCHEMA_PATH.read_text(encoding="utf-8"))
        learning = {
            "id": "learning-1",
            "experiment_id": "exp-1",
            "observed": "A start occurred.",
            "learned": "A smaller instruction reduced ambiguity.",
            "next_decision": "Repeat once.",
            "recorded_at": "2026-08-17T12:00:00Z",
            "source": "USER-REPORTED",
        }
        correction = {
            "id": "correction-1",
            "target_id": "pref-1",
            "replacement_or_action": "Remove the outdated preference.",
            "recorded_at": "2026-08-17T12:00:00Z",
        }

        def base() -> dict[str, Any]:
            record = copy.deepcopy(self.example)
            record["learning"] = [copy.deepcopy(learning)]
            record["corrections"] = [copy.deepcopy(correction)]
            return record

        selectors: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "root": lambda record: record,
            "sourcedStatement": lambda record: record["preferences"][0],
            "evidenceItem": lambda record: record["evidence"][0],
            "goal": lambda record: record["goals"][0],
            "hypothesis": lambda record: record["hypotheses"][0],
            "experiment": lambda record: record["experiments"][0],
            "scale": lambda record: record["scales"][0],
            "checkIn": lambda record: record["check_ins"][0],
            "decision": lambda record: record["decisions"][0],
            "decisionOption": lambda record: record["decisions"][0]["options"][0],
            "learning": lambda record: record["learning"][0],
            "correction": lambda record: record["corrections"][0],
        }
        object_schemas = {"root": schema}
        object_schemas.update(
            {
                name: definition
                for name, definition in schema["$defs"].items()
                if name in selectors
            }
        )

        for object_name, object_schema in object_schemas.items():
            selector = selectors[object_name]
            for field in object_schema.get("required", []):
                candidate = base()
                selector(candidate).pop(field)
                self._assert_canonical_rejection(candidate, f"{object_name}.{field}.required")

            if object_schema.get("additionalProperties") is False:
                candidate = base()
                selector(candidate)["__unexpected"] = "blocked"
                self._assert_canonical_rejection(
                    candidate, f"{object_name}.additionalProperties"
                )

            for field, declared in object_schema.get("properties", {}).items():
                resolved = declared
                if "$ref" in declared:
                    resolved = schema["$defs"][declared["$ref"].rsplit("/", 1)[1]]
                mutations: list[tuple[str, Any]] = []
                if "const" in resolved:
                    mutations.append(("const", "__different"))
                if "enum" in resolved:
                    mutations.append(("enum", "__invalid_enum"))
                value_type = resolved.get("type")
                if value_type == "string":
                    mutations.append(("type", 7))
                elif value_type == "array":
                    mutations.append(("type", {}))
                elif value_type == "boolean":
                    mutations.append(("type", "false"))
                elif value_type == "number":
                    mutations.append(("type", "not-a-number"))
                if resolved.get("minLength", 0) > 0:
                    mutations.append(("minLength", ""))
                if "maxLength" in resolved:
                    mutations.append(("maxLength", "x" * (resolved["maxLength"] + 1)))
                if "format" in resolved:
                    mutations.append(("format", "not-a-date"))
                if "pattern" in resolved:
                    mutations.append(("pattern", "contains-user@example.com"))
                if "maxItems" in resolved:
                    existing = selector(base()).get(field, [])
                    prototype = _array_prototype(field, existing, learning, correction)
                    mutations.append(
                        ("maxItems", [copy.deepcopy(prototype) for _ in range(resolved["maxItems"] + 1)])
                    )

                for rule, invalid_value in mutations:
                    candidate = base()
                    selector(candidate)[field] = invalid_value
                    self._assert_canonical_rejection(
                        candidate, f"{object_name}.{field}.{rule}"
                    )

                items = resolved.get("items", {})
                if items.get("type") == "string":
                    candidate = base()
                    selector(candidate)[field] = [4]
                    self._assert_canonical_rejection(
                        candidate, f"{object_name}.{field}.items.type"
                    )
                    if "maxLength" in items:
                        candidate = base()
                        selector(candidate)[field] = ["x" * (items["maxLength"] + 1)]
                        self._assert_canonical_rejection(
                            candidate, f"{object_name}.{field}.items.maxLength"
                        )
                elif "$ref" in items:
                    candidate = base()
                    selector(candidate)[field] = [7]
                    self._assert_canonical_rejection(
                        candidate, f"{object_name}.{field}.items.type"
                    )

    def _assert_canonical_rejection(self, candidate: Any, rule: str) -> None:
        with self.subTest(rule=rule):
            errors = growth_record.validate_against_schema(candidate)
            self.assertTrue(errors, f"mutation for {rule} was accepted")
            self.assertTrue(growth_record.validate_record(candidate))

    def test_top_level_constraints(self) -> None:
        mutations = [
            ("required", lambda x: x.pop("goals")),
            ("unknown", lambda x: x.__setitem__("profile", {})),
            ("schema-version", lambda x: x.__setitem__("schema_version", "2.0")),
            ("record-id-empty", lambda x: x.__setitem__("record_id", "")),
            ("record-id-max", lambda x: x.__setitem__("record_id", "x" * 129)),
            ("updated-format", lambda x: x.__setitem__("updated_at", "tomorrow")),
            ("purpose-type", lambda x: x.__setitem__("purpose", 3)),
            ("purpose-max", lambda x: x.__setitem__("purpose", "x" * 501)),
            ("policy-enum", lambda x: x.__setitem__("memory_policy", "ALWAYS")),
            ("boundaries-type", lambda x: x.__setitem__("boundaries", {})),
            ("boundaries-max", lambda x: x.__setitem__("boundaries", ["x"] * 21)),
            ("boundary-max", lambda x: x.__setitem__("boundaries", ["x" * 301])),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_sourced_statement_constraints(self) -> None:
        mutations = [
            ("preferences-max", lambda x: x.__setitem__("preferences", _copies(x["preferences"][0], 31))),
            ("preference-required", lambda x: x["preferences"][0].pop("statement")),
            ("preference-unknown", lambda x: x["preferences"][0].__setitem__("score", 4)),
            ("preference-id-empty", lambda x: x["preferences"][0].__setitem__("id", "")),
            ("preference-id-max", lambda x: x["preferences"][0].__setitem__("id", "x" * 129)),
            ("preference-statement-empty", lambda x: x["preferences"][0].__setitem__("statement", "")),
            ("preference-statement-max", lambda x: x["preferences"][0].__setitem__("statement", "x" * 1001)),
            ("preference-source", lambda x: x["preferences"][0].__setitem__("source", "MODEL-INFERRED")),
            ("preference-context-max", lambda x: x["preferences"][0].__setitem__("context", "x" * 501)),
            ("preference-confirmed-format", lambda x: x["preferences"][0].__setitem__("confirmed_at", "now")),
            ("preference-superseded-type", lambda x: x["preferences"][0].__setitem__("superseded", "false")),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_goal_constraints(self) -> None:
        mutations = [
            ("goals-type", lambda x: x.__setitem__("goals", {})),
            ("goals-max", lambda x: x.__setitem__("goals", _copies(x["goals"][0], 21))),
            ("goal-required", lambda x: x["goals"][0].pop("status")),
            ("goal-unknown", lambda x: x["goals"][0].__setitem__("priority", 1)),
            ("goal-statement-max", lambda x: x["goals"][0].__setitem__("statement", "x" * 1001)),
            ("goal-type-enum", lambda x: x["goals"][0].__setitem__("goal_type", "identity")),
            ("goal-status-enum", lambda x: x["goals"][0].__setitem__("status", "done-ish")),
            ("goal-source-enum", lambda x: x["goals"][0].__setitem__("source", "SYSTEM")),
            ("goal-review-format", lambda x: x["goals"][0].__setitem__("review_at", "next week")),
            ("goal-success-max", lambda x: x["goals"][0].__setitem__("success_evidence", "x" * 1001)),
            ("goal-stop-max", lambda x: x["goals"][0].__setitem__("stop_condition", "x" * 1001)),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_hypothesis_constraints(self) -> None:
        mutations = [
            ("hypotheses-max", lambda x: x.__setitem__("hypotheses", _copies(x["hypotheses"][0], 41))),
            ("hypothesis-required", lambda x: x["hypotheses"][0].pop("alternative_hypothesis_ids")),
            ("hypothesis-unknown", lambda x: x["hypotheses"][0].__setitem__("diagnosis", "none")),
            ("hypothesis-statement-max", lambda x: x["hypotheses"][0].__setitem__("statement", "x" * 1501)),
            ("hypothesis-confidence", lambda x: x["hypotheses"][0].__setitem__("confidence", 0.8)),
            ("hypothesis-source", lambda x: x["hypotheses"][0].__setitem__("source", "USER-REPORTED")),
            ("hypothesis-context-max", lambda x: x["hypotheses"][0].__setitem__("context_boundary", "x" * 1001)),
            ("supporting-max-items", lambda x: x["hypotheses"][0].__setitem__("supporting_evidence_ids", [f"e{i}" for i in range(21)])),
            ("supporting-item-max", lambda x: x["hypotheses"][0].__setitem__("supporting_evidence_ids", ["x" * 129])),
            ("disconfirming-max-items", lambda x: x["hypotheses"][0].__setitem__("disconfirming_or_missing_evidence_ids", [f"e{i}" for i in range(21)])),
            ("alternatives-max-items", lambda x: x["hypotheses"][0].__setitem__("alternative_hypothesis_ids", [f"h{i}" for i in range(11)])),
            ("alternative-item-max", lambda x: x["hypotheses"][0].__setitem__("alternative_hypothesis_ids", ["x" * 129])),
            ("hypothesis-status", lambda x: x["hypotheses"][0].__setitem__("status", "confirmed")),
            ("hypothesis-updated-format", lambda x: x["hypotheses"][0].__setitem__("updated_at", "today")),
            ("hypothesis-review-format", lambda x: x["hypotheses"][0].__setitem__("review_at", "later")),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_evidence_scale_checkin_and_decision_constraints(self) -> None:
        mutations = [
            ("evidence-required", lambda x: x["evidence"][0].pop("origin_kind")),
            ("evidence-source", lambda x: x["evidence"][0].__setitem__("source", "MODEL-INFERRED")),
            ("evidence-date", lambda x: x["evidence"][0].__setitem__("captured_at", "today")),
            ("scale-required", lambda x: x["scales"][0].pop("low_anchor")),
            ("scale-status", lambda x: x["scales"][0].__setitem__("status", "diagnostic")),
            ("checkin-user", lambda x: x["check_ins"][0].__setitem__("user_supplied", False)),
            ("checkin-value-type", lambda x: x["check_ins"][0].__setitem__("value", "high")),
            ("decision-options-min", lambda x: x["decisions"][0].__setitem__("options", [x["decisions"][0]["options"][0]])),
            ("decision-chosen-by", lambda x: x["decisions"][0].__setitem__("chosen_by", "MODEL")),
            ("decision-reversibility", lambda x: x["decisions"][0]["options"][0].__setitem__("reversibility", "irreversible")),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_experiment_constraints(self) -> None:
        mutations = [
            ("experiments-max", lambda x: x.__setitem__("experiments", _copies(x["experiments"][0], 41))),
            ("experiment-required", lambda x: x["experiments"][0].pop("action")),
            ("experiment-unknown", lambda x: x["experiments"][0].__setitem__("streak", 3)),
            ("experiment-question-max", lambda x: x["experiments"][0].__setitem__("question", "x" * 1001)),
            ("experiment-hypothesis-max", lambda x: x["experiments"][0].__setitem__("hypothesis_id", "x" * 129)),
            ("experiment-action-max", lambda x: x["experiments"][0].__setitem__("action", "x" * 1501)),
            ("experiment-trigger-max", lambda x: x["experiments"][0].__setitem__("trigger", "x" * 1001)),
            ("experiment-coping-max", lambda x: x["experiments"][0].__setitem__("coping_response", "x" * 1001)),
            ("experiment-evidence-empty", lambda x: x["experiments"][0].__setitem__("evidence", "")),
            ("experiment-start-format", lambda x: x["experiments"][0].__setitem__("start_at", "later")),
            ("experiment-review-format", lambda x: x["experiments"][0].__setitem__("review_at", "later")),
            ("experiment-stop-max", lambda x: x["experiments"][0].__setitem__("stop_condition", "x" * 1001)),
            ("experiment-status", lambda x: x["experiments"][0].__setitem__("status", "failed")),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_learning_and_correction_constraints(self) -> None:
        valid_learning = {
            "id": "learning-1",
            "experiment_id": "exp-1",
            "observed": "A start occurred.",
            "learned": "The small instruction reduced ambiguity.",
            "next_decision": "Repeat once.",
            "recorded_at": "2026-08-17T12:00:00Z",
            "source": "USER-REPORTED",
        }
        valid_correction = {
            "id": "correction-1",
            "target_id": "pref-1",
            "replacement_or_action": "Remove the outdated preference.",
            "recorded_at": "2026-08-17T12:00:00Z",
        }

        def with_learning(mutator: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
            def mutate(record: dict[str, Any]) -> None:
                record["learning"] = [copy.deepcopy(valid_learning)]
                mutator(record["learning"][0])
            return mutate

        def with_correction(mutator: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
            def mutate(record: dict[str, Any]) -> None:
                record["corrections"] = [copy.deepcopy(valid_correction)]
                mutator(record["corrections"][0])
            return mutate

        mutations = [
            ("learning-max", lambda x: x.__setitem__("learning", _copies(valid_learning, 101))),
            ("learning-required", with_learning(lambda x: x.pop("learned"))),
            ("learning-unknown", with_learning(lambda x: x.__setitem__("mood", 5))),
            ("learning-experiment-max", with_learning(lambda x: x.__setitem__("experiment_id", "x" * 129))),
            ("learning-observed-max", with_learning(lambda x: x.__setitem__("observed", "x" * 1501))),
            ("learning-learned-empty", with_learning(lambda x: x.__setitem__("learned", ""))),
            ("learning-next-max", with_learning(lambda x: x.__setitem__("next_decision", "x" * 1001))),
            ("learning-date", with_learning(lambda x: x.__setitem__("recorded_at", "yesterday"))),
            ("learning-source", with_learning(lambda x: x.__setitem__("source", "MODEL"))),
            ("corrections-max", lambda x: x.__setitem__("corrections", _copies(valid_correction, 101))),
            ("correction-required", with_correction(lambda x: x.pop("target_id"))),
            ("correction-unknown", with_correction(lambda x: x.__setitem__("reasoning", "hidden"))),
            ("correction-target-empty", with_correction(lambda x: x.__setitem__("target_id", ""))),
            ("correction-action-max", with_correction(lambda x: x.__setitem__("replacement_or_action", "x" * 1501))),
            ("correction-date", with_correction(lambda x: x.__setitem__("recorded_at", "today"))),
        ]
        for name, mutation in mutations:
            self.assert_schema_rejects(name, mutation)

    def test_semantic_integrity_not_expressible_in_schema(self) -> None:
        candidate = copy.deepcopy(self.example)
        candidate["goals"][0]["id"] = "hyp-1"
        self.assertTrue(any("duplicate id" in e for e in growth_record.validate_record(candidate)))

        candidate = copy.deepcopy(self.example)
        candidate["corrections"] = [
            {
                "id": "correction-1",
                "target_id": "not-present",
                "replacement_or_action": "Remove it.",
                "recorded_at": "2026-08-17T12:00:00Z",
            }
        ]
        self.assertEqual(growth_record.validate_against_schema(candidate), [])
        self.assertTrue(any("unknown target" in e for e in growth_record.validate_record(candidate)))


def _copies(item: dict[str, Any], count: int) -> list[dict[str, Any]]:
    result = []
    for index in range(count):
        value = copy.deepcopy(item)
        value["id"] = f"item-{index}"
        result.append(value)
    return result


def _array_prototype(
    field: str,
    existing: list[Any],
    learning: dict[str, Any],
    correction: dict[str, Any],
) -> Any:
    if existing:
        return existing[0]
    if field == "learning":
        return learning
    if field == "corrections":
        return correction
    return "x"


if __name__ == "__main__":
    unittest.main()
