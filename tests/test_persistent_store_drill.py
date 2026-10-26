from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "persistent_store_drill", ROOT / "scripts/run_persistent_store_drill.py"
)
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


class PersistentStoreDrillTests(unittest.TestCase):
    def test_complete_drill_is_schema_valid_content_free_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            os.chmod(root, 0o700)
            report = drill.run_drill(
                storage_root=root,
                record_path=ROOT / "examples/growth-record.example.json",
                named_host="test-private-host",
                environment_id="test-private-host-0001",
                candidate_commit="a" * 40,
                clock=drill.DrillClock(
                    datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
                ),
                audit_retention_days=1,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(drill.schema_errors(report), [])
            self.assertEqual(len(report["checks"]), 7)
            self.assertTrue(all(item["status"] == "PASS" for item in report["checks"]))
            self.assertEqual(list(root.iterdir()), [])
            rendered = json.dumps(report)
            self.assertNotIn("alice@example.com", rendered)
            self.assertNotIn("Understand recurring avoidance", rendered)

    def test_nonempty_store_root_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            os.chmod(root, 0o700)
            marker = root / "pgc-growth-records.json"
            marker.write_text("existing", encoding="utf-8")
            before = marker.read_bytes()
            with self.assertRaisesRegex(ValueError, "must not contain"):
                drill.run_drill(
                    storage_root=root,
                    record_path=ROOT / "examples/growth-record.example.json",
                    named_host="test-private-host",
                    environment_id="test-private-host-0001",
                    candidate_commit="a" * 40,
                    clock=drill.DrillClock(
                        datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
                    ),
                    audit_retention_days=1,
                )
            self.assertEqual(marker.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
