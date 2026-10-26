from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))

import campaign_workspace  # noqa: E402
import target_session  # noqa: E402
from tests.test_target_session import (  # noqa: E402
    ADAPTER,
    FakeClock,
    SUITE,
    config,
    review_for,
)


class CampaignWorkspaceTests(unittest.TestCase):
    def write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_initialize_exact_plan_and_surface_next_actions(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            config_path = directory / "config.json"
            cfg = config()
            self.write_json(config_path, cfg)
            root = directory / "workspace"
            manifest_path = root / "workspace.json"
            manifest = campaign_workspace.initialize_workspace(
                workspace_root=root,
                config_path=config_path,
                output=manifest_path,
                clock=FakeClock(),
                source_checker=lambda _: (cfg["source_commit"], True),
            )
            self.assertEqual(manifest["run_count"], len(cfg["run_plan"]))
            self.assertEqual(
                [item["identity"] for item in manifest["runs"]], cfg["run_plan"]
            )
            self.assertTrue((root / "target-config.json").is_file())
            self.assertEqual(
                len(list((root / "runs").glob("*/session-000.json"))),
                len(cfg["run_plan"]),
            )

            status = campaign_workspace.workspace_status(
                workspace_path=manifest_path, clock=FakeClock()
            )
            self.assertEqual(status["counts"], {"AWAITING_PROVIDER": 5})
            self.assertTrue(
                all(item["next_action"] == "CAPTURE" for item in status["runs"])
            )

            first = manifest["runs"][0]
            run_directory = root / first["directory"]
            session = target_session.TargetSession.from_artifact(
                suite=SUITE,
                config=cfg,
                artifact=json.loads(
                    (run_directory / "session-000.json").read_text(encoding="utf-8")
                ),
                clock=FakeClock(),
            )
            provider = target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=ADAPTER,
                environment={},
                clock=FakeClock(),
            )
            self.addCleanup(provider.close)
            completion = session.capture(provider)
            campaign_workspace.write_private_new(
                run_directory / "session-001.json", session.to_artifact()
            )
            status = campaign_workspace.workspace_status(
                workspace_path=manifest_path, clock=FakeClock()
            )
            self.assertEqual(
                status["runs"][0]["status"],
                "AWAITING_REVIEW_EXPORT",
                status["runs"][0],
            )
            self.assertEqual(status["runs"][0]["next_action"], "EXPORT_REVIEW")

            campaign_workspace.write_private_new(
                run_directory / "review-request.json", session.review_request()
            )
            status = campaign_workspace.workspace_status(
                workspace_path=manifest_path, clock=FakeClock()
            )
            self.assertEqual(status["runs"][0]["status"], "AWAITING_EXTERNAL_REVIEW")
            campaign_workspace.write_private_new(
                run_directory / "review-response.json",
                review_for(session, completion),
            )
            status = campaign_workspace.workspace_status(
                workspace_path=manifest_path, clock=FakeClock()
            )
            self.assertEqual(status["runs"][0]["status"], "READY_TO_IMPORT_REVIEW")
            self.assertEqual(status["runs"][0]["next_action"], "IMPORT_REVIEW")

    def test_workspace_root_swap_and_manifest_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            cfg = config()
            config_path = directory / "config.json"
            self.write_json(config_path, cfg)
            root = directory / "workspace"
            manifest_path = root / "workspace.json"
            campaign_workspace.initialize_workspace(
                workspace_root=root,
                config_path=config_path,
                output=manifest_path,
                clock=FakeClock(),
                source_checker=lambda _: (cfg["source_commit"], True),
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["runs"][0]["identity"]["repetition"] = 999
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                campaign_workspace.CampaignWorkspaceError, "self-hash mismatch"
            ):
                campaign_workspace.workspace_status(
                    workspace_path=manifest_path, clock=FakeClock()
                )


if __name__ == "__main__":
    unittest.main()
