from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> object:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_validator_module():
    path = ROOT / "scripts/validate.py"
    spec = importlib.util.spec_from_file_location("outcome_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("validator import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutcomeEvaluationTests(unittest.TestCase):
    def test_outcome_design_is_valid_and_nonqualifying(self) -> None:
        schema = load_json("evals/outcome-measures.schema.json")
        design = load_json("evals/outcome-measures.json")
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(design)), [])
        self.assertFalse(design["qualification_claim_allowed"])
        primary = [measure["id"] for measure in design["measures"] if measure["role"] == "primary"]
        self.assertEqual(primary, design["primary_outcome_ids"])
        self.assertEqual(len(primary), 2)
        self.assertEqual(len({measure["id"] for measure in design["measures"]}), len(design["measures"]))
        self.assertEqual(
            {measure["layer"] for measure in design["measures"]},
            {"process", "proximal", "delayed", "burden", "dependence"},
        )

    def test_outcome_design_rejects_posthoc_primary_substitution(self) -> None:
        design = copy.deepcopy(load_json("evals/outcome-measures.json"))
        design["primary_outcome_ids"][1] = "session_time_and_turn_burden"
        errors = load_validator_module().validate_outcome_design(design)
        self.assertIn("primary outcome ids must exactly match measures marked primary", errors)

    def test_session_capsule_example_and_persistence_states(self) -> None:
        schema = load_json("skill/personal-growth-copilot/assets/session-capsule.schema.json")
        example = load_json("examples/session-capsule.example.json")
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(example)), [])

        missing_receipt = copy.deepcopy(example)
        missing_receipt["persistence"]["status"] = "confirmed_by_host"
        self.assertTrue(list(validator.iter_errors(missing_receipt)))

        false_not_requested = copy.deepcopy(example)
        false_not_requested["persistence"]["status"] = "not_requested"
        self.assertTrue(list(validator.iter_errors(false_not_requested)))

        hidden_field = copy.deepcopy(example)
        hidden_field["raw_transcript"] = "must not be retained"
        self.assertTrue(list(validator.iter_errors(hidden_field)))

    def test_strong_comparators_remain_design_only_and_match_capabilities(self) -> None:
        for comparator_id in ("strong_generalist", "minimal_visible_model"):
            comparator = yaml.safe_load(
                (ROOT / f"evals/comparators/{comparator_id}.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(comparator["comparator_id"], comparator_id)
            self.assertEqual(comparator["status"], "design-only-unexecuted")
            self.assertTrue(comparator["same_model_required"])
            self.assertTrue(comparator["same_safety_policy_required"])
            self.assertTrue(comparator["same_context_access_required"])
            self.assertEqual(comparator["memory_policy"], "READ_ONLY_USER_APPROVED")


if __name__ == "__main__":
    unittest.main()
