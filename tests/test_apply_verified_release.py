from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "apply_verified_release_runtime", ROOT / "scripts/apply_verified_release.py"
)
application = importlib.util.module_from_spec(spec)
spec.loader.exec_module(application)


class ApplyVerifiedReleaseTests(unittest.TestCase):
    def test_promoted_current_verification_creates_bound_manifest(self):
        commit = "a" * 40
        result = application.build_manifest(
            index_path=Path("index.json"),
            policy_path=Path("policy.json"),
            expected_commit=commit,
            expected_policy_sha256="b" * 64,
            expected_index_sha256="c" * 64,
            release="0.5.0-alpha.1",
            generated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            verifier=lambda **_: {
                "verification_status": "pass",
                "release_status": "PROMOTED",
                "candidate_commit": commit,
                "verified_gate_count": 9,
                "qualification_update_allowed": True,
                "errors": [],
            },
        )
        self.assertEqual(manifest := result["status"], "PROMOTED")
        self.assertTrue(result["qualification_update_allowed"])
        self.assertEqual(len(result["manifest_sha256"]), 64)

    def test_failed_eligible_or_partial_packets_cannot_create_release_manifest(self):
        base = {
            "verification_status": "pass",
            "release_status": "PROMOTED",
            "candidate_commit": "a" * 40,
            "verified_gate_count": 9,
            "qualification_update_allowed": True,
            "errors": [],
        }
        for mutation in ("fail", "eligible", "partial", "other-candidate"):
            value = dict(base)
            if mutation == "fail":
                value["verification_status"] = "fail"
                value["errors"] = ["bad receipt"]
            elif mutation == "eligible":
                value["release_status"] = "ELIGIBLE"
                value["qualification_update_allowed"] = False
            elif mutation == "partial":
                value["verified_gate_count"] = 8
            else:
                value["candidate_commit"] = "d" * 40
            with self.subTest(mutation=mutation), self.assertRaises(
                application.ReleaseApplicationError
            ):
                application.build_manifest(
                    index_path=Path("index.json"),
                    policy_path=Path("policy.json"),
                    expected_commit="a" * 40,
                    expected_policy_sha256="b" * 64,
                    expected_index_sha256="c" * 64,
                    release="0.5.0-alpha.1",
                    generated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
                    verifier=lambda **_: value,
                )


if __name__ == "__main__":
    unittest.main()
