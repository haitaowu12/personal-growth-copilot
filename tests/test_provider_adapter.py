from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import target_session  # noqa: E402
from providers import codex_cli_adapter  # noqa: E402
from tests.test_target_session import FakeClock, SUITE, config  # noqa: E402

ADAPTER = ROOT / "providers/codex_cli_adapter.py"


class ProviderAdapterTests(unittest.TestCase):
    def fake_codex(
        self,
        directory: Path,
        *,
        name: str = "fake-codex",
        event_statement: str = (
            'print(json.dumps({"type": "thread.started", '
            '"thread_id": "thread_fixture_0001"}))'
        ),
    ) -> Path:
        path = directory / name
        path.write_text(
            """#!/usr/bin/env python3
import json
import pathlib
import sys

prompt = sys.stdin.read()
if "advice-loop-saturation" in prompt or "REFLECTED_USER_MEANING" in prompt:
    raise SystemExit(7)
args = sys.argv[1:]
output = pathlib.Path(args[args.index("--output-last-message") + 1])
output.write_text(json.dumps({
    "text": "I hear that you want help without turning this into an interrogation. What one detail would most change what feels useful next?",
    "resource_claims": [],
}), encoding="utf-8")
"""
            + event_statement
            + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o700)
        return path

    def adapter_config(self, fake_codex: Path) -> dict:
        cfg = config()
        cfg["provider"].update(
            {
                "adapter_sha256": hashlib.sha256(ADAPTER.read_bytes()).hexdigest(),
                "adapter_version": "codex-cli-adapter-test",
                "runtime_executable_sha256": hashlib.sha256(
                    fake_codex.read_bytes()
                ).hexdigest(),
                "host": "codex-cli",
                "model": "fixture-model",
                "model_version": "fixture-model-v1",
                "settings": {"reasoning_effort": "low"},
                "tool_permissions": [],
                "environment_allowlist": [
                    "PGC_CODEX_AUTH_ROOT",
                    "PGC_CODEX_BIN",
                    "PGC_EVAL_REPO_ROOT",
                ],
            }
        )
        return cfg

    def test_codex_adapter_uses_bound_profile_without_case_or_gold_label_leakage(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            fake_codex = self.fake_codex(directory)
            auth_root = directory / "auth"
            auth_root.mkdir()
            cfg = self.adapter_config(fake_codex)
            session = target_session.TargetSession(
                suite=SUITE,
                config=cfg,
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
            provider = target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=ADAPTER,
                environment={
                    "PGC_CODEX_AUTH_ROOT": str(auth_root),
                    "PGC_CODEX_BIN": str(fake_codex),
                    "PGC_EVAL_REPO_ROOT": str(ROOT),
                },
                clock=FakeClock(),
            )
            try:
                completion = session.capture(provider)
            finally:
                provider.close()
            self.assertIn("without turning this into an interrogation", completion.text)
            self.assertEqual(completion.resource_claims, ())
            self.assertFalse(completion.memory_write_attempted)
            self.assertEqual(completion.provider_response_id, "codex-thread_fixture_0001")

    def test_codex_adapter_rejects_a_changed_profile_bundle(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            fake_codex = self.fake_codex(directory)
            auth_root = directory / "auth"
            auth_root.mkdir()
            shadow = directory / "shadow"
            for relative in (
                "plugins/personal-growth-copilot",
                "evals/baselines",
                "providers",
            ):
                source = ROOT / relative
                destination = shadow / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            changed = shadow / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references/context-model.md"
            changed.write_text(changed.read_text(encoding="utf-8") + "\nchanged\n")
            cfg = self.adapter_config(fake_codex)
            session = target_session.TargetSession(
                suite=SUITE,
                config=cfg,
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
            provider = target_session.FrozenStdioProvider(
                config=cfg,
                adapter_path=ADAPTER,
                environment={
                    "PGC_CODEX_AUTH_ROOT": str(auth_root),
                    "PGC_CODEX_BIN": str(fake_codex),
                    "PGC_EVAL_REPO_ROOT": str(shadow),
                },
                clock=FakeClock(),
            )
            try:
                with self.assertRaises(target_session.ProviderProtocolError):
                    session.capture(provider)
            finally:
                provider.close()

    def test_profile_hash_and_prompt_use_the_same_opened_bytes(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            fake_codex = self.fake_codex(directory)
            shadow = directory / "shadow"
            for relative in (
                "plugins/personal-growth-copilot",
                "evals/baselines",
                "providers",
            ):
                source = ROOT / relative
                destination = shadow / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            cfg = self.adapter_config(fake_codex)
            session = target_session.TargetSession(
                suite=SUITE,
                config=cfg,
                case_id="advice-loop-saturation",
                system_id="target",
                variant_id="canonical",
                repetition=1,
                clock=FakeClock(),
            )
            payload = target_session.FrozenStdioProvider.request_payload(
                session.pending_request(), cfg
            )
            changed = shadow / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references/context-model.md"
            original_reader = codex_cli_adapter.read_regular_bytes
            mutated = False

            def mutate_after_read(path, *, maximum):
                nonlocal mutated
                data = original_reader(path, maximum=maximum)
                if path == changed and not mutated:
                    changed.write_text("INJECTED UNFROZEN PROFILE", encoding="utf-8")
                    mutated = True
                return data

            with mock.patch.object(
                codex_cli_adapter,
                "read_regular_bytes",
                side_effect=mutate_after_read,
            ):
                profile = codex_cli_adapter.load_profile(payload, shadow)
            self.assertTrue(mutated)
            self.assertNotIn("INJECTED UNFROZEN PROFILE", profile)

    def test_codex_adapter_rejects_substituted_runtime_and_incomplete_event_stream(self):
        for event_statement in (
            'print("not-json")',
            "pass",
            'print(json.dumps({"type": "thread.started", "thread_id": "thread_unknown"})); '
            'print(json.dumps({"type": "tool.used", "tool": "web_search"}))',
        ):
            with self.subTest(event_statement=event_statement):
                with tempfile.TemporaryDirectory() as directory_name:
                    directory = Path(directory_name)
                    bound = self.fake_codex(directory, name="bound")
                    substitute = self.fake_codex(
                        directory,
                        name="substitute",
                        event_statement=event_statement,
                    )
                    auth_root = directory / "auth"
                    auth_root.mkdir()
                    cfg = self.adapter_config(bound)
                    session = target_session.TargetSession(
                        suite=SUITE,
                        config=cfg,
                        case_id="advice-loop-saturation",
                        system_id="target",
                        variant_id="canonical",
                        repetition=1,
                        clock=FakeClock(),
                    )
                    provider = target_session.FrozenStdioProvider(
                        config=cfg,
                        adapter_path=ADAPTER,
                        environment={
                            "PGC_CODEX_AUTH_ROOT": str(auth_root),
                            "PGC_CODEX_BIN": str(substitute),
                            "PGC_EVAL_REPO_ROOT": str(ROOT),
                        },
                        clock=FakeClock(),
                    )
                    try:
                        with self.assertRaises(target_session.ProviderProtocolError):
                            session.capture(provider)
                    finally:
                        provider.close()

        for event_statement in ('print("not-json")', "pass"):
            with self.subTest(bound_incomplete_stream=event_statement):
                with tempfile.TemporaryDirectory() as directory_name:
                    directory = Path(directory_name)
                    incomplete = self.fake_codex(
                        directory,
                        event_statement=event_statement,
                    )
                    auth_root = directory / "auth"
                    auth_root.mkdir()
                    cfg = self.adapter_config(incomplete)
                    session = target_session.TargetSession(
                        suite=SUITE,
                        config=cfg,
                        case_id="advice-loop-saturation",
                        system_id="target",
                        variant_id="canonical",
                        repetition=1,
                        clock=FakeClock(),
                    )
                    provider = target_session.FrozenStdioProvider(
                        config=cfg,
                        adapter_path=ADAPTER,
                        environment={
                            "PGC_CODEX_AUTH_ROOT": str(auth_root),
                            "PGC_CODEX_BIN": str(incomplete),
                            "PGC_EVAL_REPO_ROOT": str(ROOT),
                        },
                        clock=FakeClock(),
                    )
                    try:
                        with self.assertRaises(target_session.ProviderProtocolError):
                            session.capture(provider)
                    finally:
                        provider.close()


if __name__ == "__main__":
    unittest.main()
