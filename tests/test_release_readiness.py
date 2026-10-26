from __future__ import annotations

import copy
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_readiness_runtime", ROOT / "scripts/release_readiness.py"
)
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReleaseReadinessTests(unittest.TestCase):
    def test_current_repository_is_repo_complete_but_external_observations_pending(self):
        report = readiness.build_report(
            datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        )
        self.assertTrue(report["repo_side_complete"])
        self.assertFalse(report["production_qualified"])
        self.assertEqual(report["status"], "REPO_COMPLETE_EXTERNAL_PENDING")
        self.assertEqual(
            [item["gate_id"] for item in report["gates"]],
            list(readiness.release_evidence.GATES),
        )
        self.assertEqual(
            set(report["external_observations_pending"]),
            set(readiness.release_evidence.GATES),
        )
        self.assertTrue(all(item["repo_status"] == "PASS" for item in report["gates"]))

    def test_missing_repo_operator_is_reported_without_becoming_external_pending(self):
        original = copy.deepcopy(readiness.GATE_MACHINERY["pilot"])
        changed = copy.deepcopy(original)
        changed["artifacts"] = [*changed["artifacts"], "scripts/absent-pilot-operator.py"]
        with mock.patch.dict(
            readiness.GATE_MACHINERY, {"pilot": changed}, clear=False
        ):
            report = readiness.build_report(
                datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
            )
        self.assertFalse(report["repo_side_complete"])
        self.assertEqual(report["status"], "REPO_GAPS")
        self.assertIn(
            "scripts/absent-pilot-operator.py", report["missing_repo_artifacts"]
        )
        pilot = next(item for item in report["gates"] if item["gate_id"] == "pilot")
        self.assertEqual(pilot["repo_status"], "FAIL")

    def test_external_work_plan_covers_exact_gates_without_claiming_evidence(self):
        plan = readiness.build_work_plan(
            candidate_commit="a" * 40,
            qualification_plan_sha256="b" * 64,
            generated_at=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
            hard_invariants=(
                "Never fabricate identity, independence, observation, signature, or gate passage.",
                "Keep candidate content outside the holdout-author workspace after freeze.",
                "Retain failures, retries, withdrawals, missing reviews, and non-attempts.",
                "Keep production persistence disabled until the privacy gate authorizes it.",
                "Require independent review before explicit owner promotion.",
            ),
        )
        self.assertEqual(plan["status"], "AWAITING_EXTERNAL_OBSERVATIONS")
        self.assertEqual(plan["execution_order"], list(readiness.release_evidence.GATES))
        self.assertEqual(len(plan["gates"]), 9)
        self.assertNotIn("PASS", plan["claim_limit"])
        self.assertTrue(
            all(item["external_observations"] for item in plan["gates"])
        )


if __name__ == "__main__":
    unittest.main()
