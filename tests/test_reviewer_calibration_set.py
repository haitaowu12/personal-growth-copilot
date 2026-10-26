from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


class ReviewerCalibrationSetTests(unittest.TestCase):
    def test_calibration_set_is_schema_valid_system_blinded_and_covers_key_risks(self):
        value = json.loads(
            (ROOT / "evals/reviewer-calibration-set.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            (ROOT / "evals/reviewer-calibration-set.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value)
        )
        self.assertEqual(errors, [])
        self.assertFalse(value["holdout"])
        self.assertTrue(value["system_identity_omitted"])
        self.assertGreaterEqual(len(value["examples"]), 4)
        self.assertIn("zh", {item["language"] for item in value["examples"]})
        self.assertIn("critical", {item["risk"] for item in value["examples"]})
        hard_codes = {
            code
            for item in value["examples"]
            for code in item["expected_hard_failure_codes"]
        }
        self.assertIn("DEPENDENCE_LANGUAGE", hard_codes)
        self.assertIn("FABRICATED_RESOURCE", hard_codes)

    def test_calibration_ids_and_transcripts_are_unique(self):
        value = json.loads(
            (ROOT / "evals/reviewer-calibration-set.json").read_text(
                encoding="utf-8"
            )
        )
        ids = [item["id"] for item in value["examples"]]
        transcripts = [
            json.dumps(item["transcript"], sort_keys=True, ensure_ascii=False)
            for item in value["examples"]
        ]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(transcripts), len(set(transcripts)))


if __name__ == "__main__":
    unittest.main()
