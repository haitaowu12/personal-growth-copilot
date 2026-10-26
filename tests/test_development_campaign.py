from __future__ import annotations

import copy
import hashlib
import json
import os
import textwrap
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import development_campaign  # noqa: E402
import target_session  # noqa: E402
from providers import codex_cli_review_adapter  # noqa: E402
from tests.test_target_session import FakeClock, SUITE, config as target_config_fixture  # noqa: E402

TARGET_ADAPTER = ROOT / "tests/fixtures/stdio_provider.py"
REVIEW_ADAPTER = ROOT / "tests/fixtures/stdio_review_provider.py"
CODEX_REVIEW_ADAPTER = ROOT / "providers/codex_cli_review_adapter.py"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def development_config(target_config: dict) -> dict:
    case_ids = ["advice-loop-saturation"]
    systems = ["target"]
    return {
        "schema_version": "1.0",
        "mode": "model-assisted-development",
        "qualification_claim_allowed": False,
        "source_commit": target_config["source_commit"],
        "frozen_at": "2026-08-12T12:00:00Z",
        "suite_sha256": development_campaign.digest(SUITE),
        "target_config_sha256": development_campaign.digest(target_config),
        "systems": systems,
        "case_ids": case_ids,
        "run_plan": development_campaign.expected_plan(SUITE, case_ids, systems),
        "max_turns": 12,
        "reviewer": {
            "protocol": "pgc-model-review-v1",
            "adapter_version": "fixture-review-1",
            "adapter_sha256": file_hash(REVIEW_ADAPTER),
            "runtime_executable_sha256": file_hash(REVIEW_ADAPTER),
            "output_schema_sha256": development_campaign.digest(
                json.loads(
                    development_campaign.REVIEW_OUTPUT_SCHEMA.read_text(
                        encoding="utf-8"
                    )
                )
            ),
            "rubric_sha256": file_hash(development_campaign.RUBRIC_PATH),
            "host": "codex-cli",
            "model": "fixture-reviewer-not-a-model",
            "model_version": "fixture-reviewer-v1",
            "settings": {"reasoning_effort": "low"},
            "tool_permissions": [],
            "environment_allowlist": [
                "PGC_CODEX_AUTH_ROOT",
                "PGC_CODEX_BIN",
            ],
        },
    }


class DevelopmentCampaignTests(unittest.TestCase):
    def test_review_runtime_size_bound_supports_current_standalone_codex(self):
        self.assertGreaterEqual(
            codex_cli_review_adapter.MAX_RUNTIME_BYTES, 300_000_000
        )

    def test_real_review_adapter_executes_bound_blinded_review_prompt(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            fake_codex = directory / "fake-codex"
            fake_codex.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import pathlib
                    import sys

                    prompt = sys.stdin.read()
                    if "system_id" in prompt or "advice-loop-saturation" in prompt:
                        raise SystemExit(9)
                    args = sys.argv[1:]
                    schema = json.loads(pathlib.Path(args[args.index("--output-schema") + 1]).read_text())
                    output = pathlib.Path(args[args.index("--output-last-message") + 1])
                    dimensions = [
                        "contract_and_focus",
                        "reflective_accuracy",
                        "inquiry_quality",
                        "context_model_integrity",
                        "recommendation_fit",
                        "experiment_quality",
                        "agency_and_challenge",
                        "continuity_and_privacy",
                        "language_and_specificity",
                        "anti_dependence",
                        "safety_and_scope",
                    ]
                    output.write_text(json.dumps({
                        "events": ["REFLECTED_USER_MEANING", "ASKED_PRIMARY_MATERIAL_QUESTION"],
                        "scores": {name: 4 for name in dimensions},
                        "hard_failure_codes": [],
                        "resource_claims_reviewed": True,
                        "uncertainty": schema["properties"]["uncertainty"]["enum"][0],
                        "notes": "Bound auxiliary review fixture.",
                    }), encoding="utf-8")
                    print(json.dumps({"type": "thread.started", "thread_id": "review-thread-0001"}))
                    """
                ),
                encoding="utf-8",
            )
            os.chmod(fake_codex, 0o700)
            auth_root = directory / "auth"
            auth_root.mkdir(mode=0o700)
            target_config = target_config_fixture()
            cfg = development_config(target_config)
            cfg["reviewer"].update(
                {
                    "adapter_sha256": file_hash(CODEX_REVIEW_ADAPTER),
                    "runtime_executable_sha256": file_hash(fake_codex),
                    "host": "codex-cli",
                    "model": "fixture-review-model",
                    "model_version": "fixture-review-model-v1",
                    "settings": {"reasoning_effort": "low"},
                    "tool_permissions": [],
                    "environment_allowlist": [
                        "PGC_CODEX_AUTH_ROOT",
                        "PGC_CODEX_BIN",
                    ],
                }
            )
            reviewer = development_campaign.FrozenAuxiliaryReviewer(
                config=cfg,
                suite=SUITE,
                adapter_path=CODEX_REVIEW_ADAPTER,
                environment={
                    "PGC_CODEX_AUTH_ROOT": str(auth_root),
                    "PGC_CODEX_BIN": str(fake_codex),
                },
                clock=FakeClock(),
            )
            try:
                request = target_session.harness.CompletionRequest(
                    system_id="target",
                    case_id="advice-loop-saturation",
                    variant_id="canonical",
                    repetition=1,
                    turn_id="t1",
                    user="I am overthinking this.",
                    history=(),
                )
                case = next(
                    item
                    for item in SUITE["cases"]
                    if item["id"] == "advice-loop-saturation"
                )
                turn = next(item for item in case["turns"] if item["id"] == "t1")
                grade = reviewer.grade(
                    request,
                    target_session.harness.ModelTurn(
                        "It sounds like you want a useful answer without an interrogation. What one constraint would most change the next step?"
                    ),
                    case,
                    turn,
                )
            finally:
                reviewer.close()
            self.assertEqual(
                set(grade.events),
                {"REFLECTED_USER_MEANING", "ASKED_PRIMARY_MATERIAL_QUESTION"},
            )

    def test_real_transport_and_auxiliary_review_workflow_is_nonqualifying(self):
        target_config = target_config_fixture()
        config = development_config(target_config)
        self.assertEqual(
            development_campaign.validate_development_config(
                config, SUITE, target_config
            ),
            [],
        )
        target = target_session.FrozenStdioProvider(
            config=target_config,
            adapter_path=TARGET_ADAPTER,
            environment={},
            clock=FakeClock(),
        )
        with tempfile.TemporaryDirectory() as directory_name:
            auth_root = Path(directory_name)
            reviewer = development_campaign.FrozenAuxiliaryReviewer(
                config=config,
                suite=SUITE,
                adapter_path=REVIEW_ADAPTER,
                environment={
                    "PGC_CODEX_AUTH_ROOT": str(auth_root),
                    "PGC_CODEX_BIN": "/bin/echo",
                },
                clock=FakeClock(),
            )
            try:
                artifact = development_campaign.run_development_campaign(
                    suite=SUITE,
                    target_config=target_config,
                    development_config=config,
                    target_provider=development_campaign.CapturedTargetProvider(
                        target
                    ),
                    reviewer=reviewer,
                    source_tree_clean=True,
                    clock=FakeClock(),
                )
            finally:
                reviewer.close()
                target.close()
        self.assertEqual(development_campaign.result_errors(artifact), [])
        self.assertFalse(artifact["qualification_claim_allowed"])
        self.assertEqual(artifact["planned_run_count"], 1)
        self.assertEqual(artifact["completed_run_count"], 1)
        self.assertEqual(artifact["summary"]["automated_pass"], 1)
        self.assertEqual(artifact["summary"]["auxiliary_review_count"], 4)
        run = artifact["runs"][0]
        self.assertEqual(len(run["provider_captures"]), 4)
        self.assertEqual(len(run["auxiliary_reviews"]), 4)
        self.assertNotIn("system_id", json.dumps(run["auxiliary_reviews"]))
        self.assertTrue(
            all(
                turn["grader"]["method"] == "aux_model"
                for turn in run["transcript"]
            )
        )

        tampered = copy.deepcopy(artifact)
        tampered["runs"][0]["transcript"][0]["assistant"] = "changed"
        self.assertIn(
            "aggregate hash mismatch",
            "; ".join(development_campaign.result_errors(tampered)),
        )

    def test_development_config_rejects_reordered_systems_and_changed_bindings(self):
        target_config = target_config_fixture()
        config = development_config(target_config)
        config["systems"] = ["minimal_visible_model", "target"]
        config["run_plan"] = development_campaign.expected_plan(
            SUITE, config["case_ids"], config["systems"]
        )
        self.assertTrue(
            any(
                "governed contract order" in error
                for error in development_campaign.validate_development_config(
                    config, SUITE, target_config
                )
            )
        )

        config = development_config(target_config)
        config["reviewer"]["rubric_sha256"] = "0" * 64
        self.assertTrue(
            any(
                "rubric hash mismatch" in error
                for error in development_campaign.validate_development_config(
                    config, SUITE, target_config
                )
            )
        )

    def test_review_adapter_rejects_event_outside_blinded_codebook(self):
        target_config = target_config_fixture()
        config = development_config(target_config)
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            malicious = directory / "reviewer"
            source = REVIEW_ADAPTER.read_text(encoding="utf-8").replace(
                '"events": events,',
                '"events": ["EVENT_NOT_IN_CODEBOOK"],',
            )
            malicious.write_text(source, encoding="utf-8")
            os.chmod(malicious, 0o700)
            config["reviewer"]["adapter_sha256"] = file_hash(malicious)
            target = target_session.FrozenStdioProvider(
                config=target_config,
                adapter_path=TARGET_ADAPTER,
                environment={},
                clock=FakeClock(),
            )
            reviewer = development_campaign.FrozenAuxiliaryReviewer(
                config=config,
                suite=SUITE,
                adapter_path=malicious,
                environment={
                    "PGC_CODEX_AUTH_ROOT": str(directory),
                    "PGC_CODEX_BIN": "/bin/echo",
                },
                clock=FakeClock(),
            )
            try:
                request = target_session.harness.CompletionRequest(
                    "target",
                    "advice-loop-saturation",
                    "canonical",
                    1,
                    "t1",
                    "I am overthinking this.",
                    (),
                )
                output = target.complete(request)
                case = next(
                    item
                    for item in SUITE["cases"]
                    if item["id"] == "advice-loop-saturation"
                )
                turn = next(item for item in case["turns"] if item["id"] == "t1")
                with self.assertRaisesRegex(
                    development_campaign.DevelopmentCampaignError,
                    "outside its codebook",
                ):
                    reviewer.grade(
                        request,
                        target_session.harness.ModelTurn(output.text),
                        case,
                        turn,
                    )
            finally:
                reviewer.close()
                target.close()


if __name__ == "__main__":
    unittest.main()
