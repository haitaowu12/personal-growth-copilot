from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "exact_head", ROOT / "scripts/verify_exact_head_ci.py"
)
exact_head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exact_head)


class ExactHeadCiTests(unittest.TestCase):
    def test_passing_receipt_is_bound_to_exact_checkout(self):
        with tempfile.TemporaryDirectory() as directory_name:
            path = Path(directory_name) / "qualification.json"
            commit = "a" * 40
            receipt = {
                "status": "pass",
                "source_tree_clean": True,
                "source_commit": commit,
                "aggregate_sha256": "b" * 64,
            }
            path.write_text(json.dumps(receipt), encoding="utf-8")
            report = exact_head.build_report(
                qualification_path=path,
                expected_sha=commit,
                checkout_sha=commit,
                workflow_ref="repo/.github/workflows/ci.yml@refs/pull/1/merge",
                generated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(
                report["qualification_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_dirty_failing_or_mismatched_receipts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory_name:
            path = Path(directory_name) / "qualification.json"
            base = {
                "status": "pass",
                "source_tree_clean": True,
                "source_commit": "a" * 40,
                "aggregate_sha256": "b" * 64,
            }
            for mutation in ("dirty", "failed", "mismatch"):
                value = dict(base)
                if mutation == "dirty":
                    value["source_tree_clean"] = False
                elif mutation == "failed":
                    value["status"] = "fail"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    exact_head.build_report(
                        qualification_path=path,
                        expected_sha="c" * 40 if mutation == "mismatch" else "a" * 40,
                        checkout_sha="a" * 40,
                        workflow_ref="test",
                        generated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
                    )


if __name__ == "__main__":
    unittest.main()
