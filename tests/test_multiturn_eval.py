from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "evals/run.py"
spec = importlib.util.spec_from_file_location("pgc_eval_run", RUNNER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("evaluation runner import failed")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

SUITE = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
CONFIG = json.loads(
    (ROOT / "evals/configs/conformance.json").read_text(encoding="utf-8")
)


class AlternateBranchGrader(runner.ConformanceGrader):
    def grade(self, request, output, case, turn):
        if case["id"] == "advice-loop-saturation" and turn["id"] == "t1":
            return runner.TurnGrade(
                events=("GENERIC_PRODUCTIVITY_PLAN",),
                grader_id="alternate-branch-fixture",
                grader_version="1.0",
                method="synthetic_fixture",
            )
        return super().grade(request, output, case, turn)


class MemoryWritingProvider(runner.ConformanceProvider):
    def complete(self, request):
        base = super().complete(request)
        return runner.ModelTurn(text=base.text, memory_write_attempted=True)


class FabricatingProvider(runner.ConformanceProvider):
    def complete(self, request):
        base = super().complete(request)
        return runner.ModelTurn(
            text=base.text,
            resource_claims=(
                {
                    "name": "Invented Service",
                    "contact": "invented-contact",
                    "source_uri": "https://invented.invalid/resource",
                },
            ),
        )


class FabricatedTextProvider(runner.ConformanceProvider):
    def complete(self, request):
        return runner.ModelTurn(
            text="Call Invented Crisis Line at +1 (555) 010-9999 right now."
        )


class UnreviewedResourceGrader(runner.ConformanceGrader):
    def grade(self, request, output, case, turn):
        return runner.TurnGrade(
            events=tuple(turn["expected_events"]),
            grader_id="unreviewed-fixture",
            grader_version="1.0",
            method="synthetic_fixture",
            resource_claims_reviewed=False,
        )


class MutatingGrader(runner.ConformanceGrader):
    def grade(self, request, output, case, turn):
        case["setup"]["memory_fixture"] = "stale"
        turn["expected_events"].append("MUTATED_BY_GRADER")
        return super().grade(request, output, case, turn)


class MutatingConfigProvider(runner.ConformanceProvider):
    def __init__(self, caller_config):
        self.caller_config = caller_config

    def complete(self, request):
        self.caller_config["frozen_at"] = "2030-01-01T00:00:00Z"
        self.caller_config["systems"] = ["target"]
        return super().complete(request)


def execute(*, case_id=None, provider=None, grader=None):
    config = deepcopy(CONFIG)
    if case_id:
        config["case_ids"] = [case_id]
    return runner.run_suite(
        suite=SUITE,
        config=config,
        provider=provider or runner.ConformanceProvider(),
        grader=grader or runner.ConformanceGrader(),
        source_commit="abcdef1234567890",
        source_tree_clean=False,
    )


class MultiTurnHarnessTests(unittest.TestCase):
    def test_full_conformance_is_reproducible_and_hash_bound(self):
        first = execute()
        second = execute()
        self.assertEqual(first["run_count"], 309)
        self.assertEqual(first["summary"]["automated_fail"], 0)
        self.assertEqual(first["summary"]["hard_failure_runs"], 0)
        self.assertEqual(first["aggregate_sha256"], second["aggregate_sha256"])
        self.assertTrue(runner.verify_result_hash(first))
        tampered = deepcopy(first)
        tampered["runs"][0]["transcript"][0]["assistant"] = "changed"
        self.assertFalse(runner.verify_result_hash(tampered))
        tampered["aggregate_sha256"] = runner._digest(
            {key: value for key, value in tampered.items() if key != "aggregate_sha256"}
        )
        self.assertFalse(runner.verify_result_hash(tampered))
        self.assertEqual(
            {run["system_id"] for run in first["runs"]},
            {"target", "direct_assistant", "structured_reflection"},
        )
        self.assertEqual(
            set(first["config"]["baseline_sha256"]),
            {"direct_assistant", "structured_reflection"},
        )
        self.assertTrue(
            all(len(value) == 64 for value in first["config"]["baseline_sha256"].values())
        )

    def test_alternate_failure_branch_is_executed_and_reported(self):
        artifact = execute(
            case_id="advice-loop-saturation", grader=AlternateBranchGrader()
        )
        self.assertEqual(artifact["run_count"], 3)
        self.assertEqual(artifact["summary"]["automated_fail"], 3)
        for run in artifact["runs"]:
            self.assertEqual(run["transcript"][0]["selected_branch"], "bad-plan")
            self.assertEqual(run["transcript"][1]["turn_id"], "t2_bad")
            self.assertIn(
                "FORBIDDEN_EVENT_OBSERVED",
                {failure["code"] for failure in run["failures"]},
            )

    def test_restricted_memory_write_is_a_hard_failure(self):
        artifact = execute(
            case_id="indirect-crisis-resource-failure",
            provider=MemoryWritingProvider(),
        )
        self.assertEqual(artifact["summary"]["hard_failure_runs"], artifact["run_count"])
        for run in artifact["runs"]:
            self.assertIn(
                "RESTRICTED_MEMORY_WRITE",
                {failure["code"] for failure in run["hard_failures"]},
            )

    def test_unverified_resource_claim_is_a_hard_failure(self):
        artifact = execute(
            case_id="indirect-crisis-resource-failure",
            provider=FabricatingProvider(),
        )
        self.assertEqual(artifact["summary"]["hard_failure_runs"], artifact["run_count"])
        for run in artifact["runs"]:
            self.assertIn(
                "FABRICATED_RESOURCE",
                {failure["code"] for failure in run["hard_failures"]},
            )

    def test_contact_text_without_claim_metadata_is_a_hard_failure(self):
        artifact = execute(
            case_id="indirect-crisis-resource-failure",
            provider=FabricatedTextProvider(),
        )
        self.assertEqual(artifact["summary"]["hard_failure_runs"], artifact["run_count"])
        for run in artifact["runs"]:
            self.assertIn(
                "FABRICATED_RESOURCE",
                {failure["code"] for failure in run["hard_failures"]},
            )

    def test_acute_resource_output_requires_complete_claim_review(self):
        artifact = execute(
            case_id="indirect-crisis-resource-failure",
            grader=UnreviewedResourceGrader(),
        )
        self.assertEqual(artifact["summary"]["hard_failure_runs"], artifact["run_count"])
        for run in artifact["runs"]:
            self.assertIn(
                "RESOURCE_CLAIMS_UNREVIEWED",
                {failure["code"] for failure in run["hard_failures"]},
            )

    def test_baseline_memory_policy_and_unscoped_target_write_are_enforced(self):
        artifact = execute(
            case_id="advice-loop-saturation",
            provider=MemoryWritingProvider(),
        )
        for run in artifact["runs"]:
            codes = {failure["code"] for failure in run["hard_failures"]}
            self.assertIn("UNAUTHORIZED_MEMORY_WRITE", codes)
            if run["system_id"] != "target":
                self.assertIn("BASELINE_MEMORY_POLICY_VIOLATION", codes)

    def test_configuration_cannot_silently_drop_a_baseline(self):
        config = deepcopy(CONFIG)
        config["systems"] = ["target", "direct_assistant"]
        with self.assertRaises(ValueError):
            runner.run_suite(
                suite=SUITE,
                config=config,
                provider=runner.ConformanceProvider(),
                grader=runner.ConformanceGrader(),
                source_commit="abcdef1234567890",
                source_tree_clean=True,
            )
        config = deepcopy(CONFIG)
        config["systems"].append("target")
        with self.assertRaises(ValueError):
            runner.run_suite(
                suite=SUITE,
                config=config,
                provider=runner.ConformanceProvider(),
                grader=runner.ConformanceGrader(),
                source_commit="abcdef1234567890",
                source_tree_clean=True,
            )

    def test_manifest_rejects_duplicate_variant_and_branch_predicates(self):
        suite = deepcopy(SUITE)
        case = next(item for item in suite["cases"] if item["id"] == "correction-under-pressure")
        case["entry_variants"][1]["id"] = case["entry_variants"][2]["id"]
        self.assertTrue(
            any("variant ids must be unique" in error for error in runner.validate_suite(suite))
        )
        suite = deepcopy(SUITE)
        turn = suite["cases"][0]["turns"][0]
        turn["branches"][0]["when_all"] = list(turn["branches"][1]["when_all"])
        turn["branches"][0]["when_none"] = list(turn["branches"][1]["when_none"])
        self.assertTrue(
            any("duplicate branch predicate" in error for error in runner.validate_suite(suite))
        )

    def test_grader_cannot_mutate_hashed_suite_or_case(self):
        original = deepcopy(SUITE)
        artifact = execute(
            case_id="advice-loop-saturation",
            grader=MutatingGrader(),
        )
        self.assertEqual(SUITE, original)
        case = next(item for item in original["cases"] if item["id"] == "advice-loop-saturation")
        self.assertTrue(all(run["case_sha256"] == runner._digest(case) for run in artifact["runs"]))
        self.assertTrue(runner.verify_result_hash(artifact, suite=original))

    def test_provider_cannot_mutate_effective_config_or_artifact_times(self):
        config = deepcopy(CONFIG)
        original = deepcopy(config)
        config["case_ids"] = ["advice-loop-saturation"]
        original["case_ids"] = ["advice-loop-saturation"]
        artifact = runner.run_suite(
            suite=SUITE,
            config=config,
            provider=MutatingConfigProvider(config),
            grader=runner.ConformanceGrader(),
            source_commit="abcdef1234567890",
            source_tree_clean=False,
        )
        self.assertNotEqual(config, original)
        self.assertEqual(artifact["config"]["frozen_at"], original["frozen_at"])
        self.assertEqual(artifact["config"]["systems"], original["systems"])
        self.assertEqual(artifact["started_at"], original["frozen_at"])
        self.assertEqual(artifact["finished_at"], original["frozen_at"])
        self.assertTrue(runner.verify_result_hash(artifact, suite=SUITE))

        tampered = deepcopy(artifact)
        tampered["runs"][0]["transcript"][0]["timestamp"] = "2030-01-01T00:00:00Z"
        tampered["runs"][0]["transcript_sha256"] = runner._digest(
            tampered["runs"][0]["transcript"]
        )
        tampered["aggregate_sha256"] = runner._digest(
            {key: value for key, value in tampered.items() if key != "aggregate_sha256"}
        )
        self.assertFalse(runner.verify_result_hash(tampered, suite=SUITE))

        tampered = deepcopy(artifact)
        for key in ("mode", "frozen_at", "provider", "grader", "max_turns"):
            del tampered["config"][key]
        tampered["config_sha256"] = runner._digest(tampered["config"])
        tampered["aggregate_sha256"] = runner._digest(
            {key: value for key, value in tampered.items() if key != "aggregate_sha256"}
        )
        self.assertFalse(runner.verify_result_hash(tampered, suite=SUITE))


if __name__ == "__main__":
    unittest.main()
