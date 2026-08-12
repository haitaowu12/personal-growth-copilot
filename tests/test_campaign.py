from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import campaign  # noqa: E402
import target_session  # noqa: E402
from tests.test_target_session import (  # noqa: E402
    SUITE,
    FakeClock,
    config,
    review_for,
)


class InProcessProvider:
    include_system_in_response_id = True

    def __init__(self, cfg: dict):
        self._config = copy.deepcopy(cfg)
        self.identity_sha256 = target_session.provider_identity(cfg)

    def complete(self, request):
        payload = target_session.FrozenStdioProvider.request_payload(
            request, self._config
        )
        response_id = "campaign-" + target_session._digest(
            {
                "system": (
                    request.system_id
                    if self.include_system_in_response_id
                    else "shared-across-systems"
                ),
                "case": request.case_id,
                "variant": request.variant_id,
                "repetition": request.repetition,
                "turn": request.turn_id,
                "history": request.history,
            }
        )[:32]
        captured = {
            "request_sha256": target_session._digest(payload),
            "provider_identity_sha256": self.identity_sha256,
            "text": f"Campaign protocol fixture {response_id}.",
            "memory_write_attempted": False,
            "resource_claims": (),
            "provider_response_id": response_id,
            "captured_at": "2026-08-12T12:00:00Z",
        }
        return target_session.CapturedCompletion(
            **captured,
            completion_sha256=target_session._digest(captured),
        )


class ReusedAcrossRunsProvider(InProcessProvider):
    include_system_in_response_id = False


class CampaignTests(unittest.TestCase):
    def mini_suite(self) -> dict:
        suite = copy.deepcopy(SUITE)
        suite["cases"] = [
            case for case in suite["cases"] if case["id"] == "advice-loop-saturation"
        ]
        return suite

    def mini_config(self) -> tuple[dict, dict]:
        suite = self.mini_suite()
        cfg = config()
        cfg["suite_sha256"] = target_session._digest(suite)
        cfg["case_ids"] = [case["id"] for case in suite["cases"]]
        cfg["run_plan"] = target_session.expected_run_plan(
            suite, cfg["case_ids"], cfg["systems"]
        )
        return suite, cfg

    def completed_results(
        self,
        directory: Path,
        cfg: dict,
        suite: dict,
        provider_type=InProcessProvider,
    ) -> list[Path]:
        paths: list[Path] = []
        for identity in cfg["run_plan"]:
            session = target_session.TargetSession(
                suite=suite,
                config=cfg,
                case_id=identity["case_id"],
                system_id=identity["system_id"],
                variant_id=identity["variant_id"],
                repetition=identity["repetition"],
                clock=FakeClock(),
            )
            provider = provider_type(cfg)
            while session.status != "COMPLETE":
                completion = session.capture(provider)
                session.import_review(review_for(session, completion))
            artifact = target_session.finalize_session(session)
            path = directory / (
                f"{identity['case_id']}-{identity['system_id']}-"
                f"{identity['variant_id']}-{identity['repetition']}.json"
            )
            path.write_text(json.dumps(artifact), encoding="utf-8")
            paths.append(path)
        return paths

    @mock.patch.object(target_session, "validate_target_config", return_value=[])
    @mock.patch.object(target_session.harness, "validate_suite", return_value=[])
    @mock.patch.object(campaign, "_require_full_suite_scope", return_value=None)
    def test_complete_campaign_is_exact_replayable_and_identity_blocked(
        self, _scope_validation, _suite_validation, _config_validation
    ):
        suite, cfg = self.mini_config()
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            paths = self.completed_results(directory, cfg, suite)
            manifest_path = directory / "manifest.json"
            manifest = campaign.build_result_manifest(
                result_paths=paths,
                manifest_path=manifest_path,
                suite=suite,
                config=cfg,
                clock=FakeClock(),
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(
                campaign,
                "_read_result_bytes",
                wraps=campaign._read_result_bytes,
            ) as bounded_reads:
                artifact = campaign.aggregate_campaign(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )
            self.assertEqual(bounded_reads.call_count, len(paths))
            self.assertFalse(artifact["campaign_complete"])
            self.assertTrue(artifact["run_plan_coverage_complete"])
            self.assertFalse(artifact["attempt_inventory_verified"])
            self.assertEqual(artifact["planned_run_count"], 3)
            self.assertEqual(artifact["received_run_count"], 3)
            self.assertEqual(artifact["behavioral_status"], "conditional_pass")
            self.assertEqual(artifact["evidence_status"], "blocked")
            self.assertEqual(
                artifact["acceptance"]["evidence_failures"],
                [
                    "EXTERNAL_REVIEWER_ATTESTATION_RECEIPT_NOT_VERIFIED",
                    "RUN_ATTEMPT_INVENTORY_NOT_EXTERNALLY_VERIFIED",
                ],
            )
            self.assertTrue(
                campaign.verify_campaign_result(
                    artifact,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )
            )

            tampered = copy.deepcopy(artifact)
            tampered["behavioral_status"] = "fail"
            tampered["aggregate_sha256"] = campaign._digest(
                {
                    key: value
                    for key, value in tampered.items()
                    if key != "aggregate_sha256"
                }
            )
            self.assertFalse(
                campaign.verify_campaign_result(
                    tampered,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )
            )

    @mock.patch.object(target_session, "validate_target_config", return_value=[])
    @mock.patch.object(target_session.harness, "validate_suite", return_value=[])
    @mock.patch.object(campaign, "_require_full_suite_scope", return_value=None)
    def test_manifest_rejects_missing_duplicate_tampered_and_symlinked_results(
        self, _scope_validation, _suite_validation, _config_validation
    ):
        suite, cfg = self.mini_config()
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            paths = self.completed_results(directory, cfg, suite)
            manifest_path = directory / "manifest.json"
            with self.assertRaises(campaign.CampaignError):
                campaign.build_result_manifest(
                    result_paths=paths[:-1],
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )
            with self.assertRaises(campaign.CampaignError):
                campaign.build_result_manifest(
                    result_paths=[paths[0], paths[0], paths[2]],
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )
            manifest = campaign.build_result_manifest(
                result_paths=paths,
                manifest_path=manifest_path,
                suite=suite,
                config=cfg,
                clock=FakeClock(),
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            paths[0].write_text("{}", encoding="utf-8")
            with self.assertRaises(campaign.CampaignError):
                campaign.aggregate_campaign(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )

            paths[0].unlink()
            os.symlink(paths[1], paths[0])
            with self.assertRaises(campaign.CampaignError):
                campaign.aggregate_campaign(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )

    def test_campaign_aggregation_rejects_a_selected_subset_of_the_governed_suite(self):
        cfg = config()
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            paths = self.completed_results(directory, cfg, SUITE)
            manifest_path = directory / "manifest.json"
            manifest = campaign.build_result_manifest(
                result_paths=paths,
                manifest_path=manifest_path,
                suite=SUITE,
                config=cfg,
                clock=FakeClock(),
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(campaign.CampaignError):
                campaign.aggregate_campaign(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=SUITE,
                    config=cfg,
                    clock=FakeClock(),
                )

    @mock.patch.object(target_session, "validate_target_config", return_value=[])
    @mock.patch.object(target_session.harness, "validate_suite", return_value=[])
    @mock.patch.object(campaign, "_require_full_suite_scope", return_value=None)
    def test_campaign_rejects_response_ids_reused_across_runs(
        self, _scope_validation, _suite_validation, _config_validation
    ):
        suite, cfg = self.mini_config()
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            paths = self.completed_results(
                directory, cfg, suite, ReusedAcrossRunsProvider
            )
            manifest_path = directory / "manifest.json"
            manifest = campaign.build_result_manifest(
                result_paths=paths,
                manifest_path=manifest_path,
                suite=suite,
                config=cfg,
                clock=FakeClock(),
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(campaign.CampaignError, "reused"):
                campaign.aggregate_campaign(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    suite=suite,
                    config=cfg,
                    clock=FakeClock(),
                )


if __name__ == "__main__":
    unittest.main()
