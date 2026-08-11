from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "scripts/validate.py"
    spec = importlib.util.spec_from_file_location("validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("validator import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectTests(unittest.TestCase):
    def test_repository_validation(self) -> None:
        self.assertEqual(load_validator().validate(), [])

    def test_release_remains_blocked(self) -> None:
        release = json.loads(
            (ROOT / "release/qualification.json").read_text(encoding="utf-8")
        )
        self.assertEqual(release["status"], "blocked")
        self.assertFalse(release["production_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
