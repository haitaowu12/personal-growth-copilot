from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_validator():
    return load_module("validator", ROOT / "scripts/validate.py")


class ProjectTests(unittest.TestCase):
    def test_repository_validation(self) -> None:
        self.assertEqual(load_validator().validate(), [])

    def test_release_remains_blocked(self) -> None:
        release = json.loads(
            (ROOT / "release/qualification.json").read_text(encoding="utf-8")
        )
        self.assertEqual(release["status"], "blocked")
        self.assertFalse(release["production_claim_allowed"])

    def test_behavioral_contract(self) -> None:
        evaluator = load_module(
            "contract_evaluator", ROOT / "scripts/evaluate_contract.py"
        )
        self.assertEqual(evaluator.validate_cases(), [])

    def test_example_growth_record(self) -> None:
        records = load_module(
            "growth_record",
            ROOT / "skill/personal-growth-copilot/scripts/growth_record.py",
        )
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(records.validate_record(example), [])

    def test_growth_record_rejects_hidden_raw_material(self) -> None:
        records = load_module(
            "growth_record_reject",
            ROOT / "skill/personal-growth-copilot/scripts/growth_record.py",
        )
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(
                encoding="utf-8"
            )
        )
        example["preferences"][0]["raw_transcript"] = "sensitive text"
        errors = records.validate_record(example)
        self.assertTrue(any("prohibited" in error for error in errors))

    def test_growth_record_rejects_broken_reference(self) -> None:
        records = load_module(
            "growth_record_reference",
            ROOT / "skill/personal-growth-copilot/scripts/growth_record.py",
        )
        example = json.loads(
            (ROOT / "examples/growth-record.example.json").read_text(
                encoding="utf-8"
            )
        )
        example["experiments"][0]["hypothesis_id"] = "missing"
        errors = records.validate_record(example)
        self.assertTrue(any("unknown hypothesis" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
