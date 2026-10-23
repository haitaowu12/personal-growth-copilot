from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConsolidatedDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load("consolidated_builder", ROOT / "scripts/package_learning.py")
        cls.data = cls.builder.package_bytes()
        with zipfile.ZipFile(io.BytesIO(cls.data)) as archive:
            cls.files = {name: archive.read(name) for name in archive.namelist()}

    def test_extracted_skill_is_closed_without_source_checkout(self):
        self.builder.validate_runtime_references(self.files)
        self.assertIn("personal-growth-copilot/references/interpersonal/romance-dating-and-intimacy.md", self.files)
        self.assertIn("personal-growth-copilot/references/interpersonal/reciprocity-and-relationship-maintenance.md", self.files)
        # Domain coverage is a package obligation, not a claim that prompts were executed.
        for number in range(1, 13):
            prefix = f"personal-growth-copilot/references/leadership/cards/L{number:02d}-"
            self.assertEqual(sum(name.startswith(prefix) for name in self.files), 1)

    def test_missing_referenced_module_fails_even_when_present_in_checkout(self):
        files = dict(self.files)
        del files["personal-growth-copilot/references/interpersonal/romance-dating-and-intimacy.md"]
        with self.assertRaisesRegex(ValueError, "Missing or escaping"):
            self.builder.validate_runtime_references(files)

    def test_nested_parent_and_inline_helper_are_real_dependencies(self):
        files = {"personal-growth-copilot/SKILL.md": b"[module](references/nested/m.md)",
                 "personal-growth-copilot/references/nested/m.md": b"[shared](../shared.md) `scripts/calc.py`",
                 "personal-growth-copilot/references/shared.md": b"# shared",
                 "personal-growth-copilot/scripts/calc.py": b"pass"}
        self.builder.validate_runtime_references(files)
        del files["personal-growth-copilot/scripts/calc.py"]
        with self.assertRaises(ValueError):
            self.builder.validate_runtime_references(files)

    def test_encoded_escape_absolute_and_missing_targets_rejected(self):
        for target in ["../outside.md", "%2e%2e/outside.md", "/private/source.md", "file:///private/source.md", "missing.md"]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.builder.validate_runtime_references({"personal-growth-copilot/SKILL.md": f"[x]({target})".encode(), "outside.md": b"not portable"})

    def test_external_provenance_and_fragment_are_not_dependencies(self):
        self.builder.validate_runtime_references({"personal-growth-copilot/SKILL.md": b"[source](https://example.org/book#page-2) [section](#purpose)"})

    def test_status_first_calculator_runs_from_extracted_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
                archive.extractall(temp)
            skill = Path(temp) / "personal-growth-copilot"
            payload = json.loads((skill / "assets/profile-score-template.json").read_text())
            source = Path(temp) / "input.json"
            source.write_text(json.dumps(payload))
            before = source.read_bytes()
            run = subprocess.run([sys.executable, str(skill / "scripts/profile_score.py"), "--input", str(source)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = json.loads(run.stdout)["result"]
            self.assertIsNone(result["decision_fit_score"])
            self.assertIn(result["decision_status"], ("insufficient_evidence", "not_calculable", "gated", "partial"))
            self.assertEqual(source.read_bytes(), before)


class DecisionAidRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calc = load("consolidated_score", ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts/profile_score.py")
        cls.example = json.loads((ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/profile-score-template.json").read_text())

    def rated(self):
        p = copy.deepcopy(self.example)
        for item in p["dimensions"]:
            item.update(rating=5, confidence="high", unknowns=[], evidence=[{"summary": "Fictional observed task", "source": "synthetic test", "date": "2026-10-23"}])
        p["flags"] = []
        return p

    def test_complete_arithmetic_is_not_blocked_without_a_flag(self):
        result = self.calc.calculate(self.rated())
        self.assertEqual(result["decision_status"], "scored")
        self.assertEqual(result["decision_fit_score"], 100)

    def test_missing_critical_evidence_cannot_be_offset_by_high_ratings(self):
        p = self.rated()
        p["dimensions"][0]["unknowns"] = ["Decision authority disputed"]
        result = self.calc.calculate(p)
        self.assertEqual(result["decision_status"], "insufficient_evidence")
        self.assertIsNone(result["decision_fit_score"])

    def test_active_flag_blocks_even_perfect_complete_ratings(self):
        p = self.rated()
        p["flags"] = [{"type": "authority", "status": "active", "description": "Authority withheld"}]
        result = self.calc.calculate(p)
        self.assertEqual(result["decision_status"], "gated")
        self.assertIsNone(result["decision_fit_score"])

    def test_boolean_weight_and_fabricated_rating_fail_validation(self):
        for field, value in [("weight", True), ("rating", 6)]:
            p = self.rated(); p["dimensions"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.calc.calculate(p)


if __name__ == "__main__":
    unittest.main()
