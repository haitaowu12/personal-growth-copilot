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
        complete_turn: bool = True,
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
            + ("\nprint(json.dumps({'type': 'turn.started'}))\nprint(json.dumps({'type': 'turn.completed'}))" if complete_turn else "")
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

    def test_only_exact_disabled_host_notice_before_a_completed_turn_is_accepted(self):
        notice = codex_cli_adapter.DISABLED_CODE_MODE_NOTICE
        for message, before_turn, completed, accepted in [
            (notice, True, True, True),
            (notice, False, True, False),
            ("unrecognized startup failure", True, True, False),
            (None, True, False, False),
        ]:
            with self.subTest(message=message, before_turn=before_turn, completed=completed), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                statements = ["print(json.dumps({'type':'thread.started','thread_id':'thread_fixture_0001'}))"]
                if not before_turn:
                    statements.append("print(json.dumps({'type':'turn.started'}))")
                if message is not None:
                    statements.append("print(json.dumps({'type':'item.completed','item':{'type':'error','message':" + repr(message) + "}}))")
                if before_turn and completed:
                    statements.append("print(json.dumps({'type':'turn.started'}))")
                if completed:
                    statements.append("print(json.dumps({'type':'turn.completed'}))")
                runtime = self.fake_codex(directory, complete_turn=False, event_statement="; ".join(statements))
                auth = directory / "auth"; auth.mkdir()
                cfg = self.adapter_config(runtime)
                payload = {"provider_execution": {key: cfg["provider"][key] for key in ["settings", "host", "model", "runtime_executable_sha256", "tool_permissions"]}}
                with mock.patch.dict(os.environ, {"PGC_CODEX_BIN":str(runtime), "PGC_CODEX_AUTH_ROOT":str(auth)}):
                    if accepted:
                        result, response = codex_cli_adapter.invoke_codex(payload, "fixture user prompt", ROOT)
                        self.assertTrue(result["text"])
                        self.assertTrue(response.startswith("codex-"))
                    else:
                        with self.assertRaises(SystemExit):
                            codex_cli_adapter.invoke_codex(payload, "fixture user prompt", ROOT)

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

    def test_codex_adapter_rejects_a_changed_nested_specialist_profile(self):
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
            changed = shadow / "plugins/personal-growth-copilot/skills/personal-growth-copilot/references/interpersonal/romance-dating-and-intimacy.md"
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


class MacBundleSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "vendor/Runtime.app/Contents/MacOS/codex"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"bound executable fixture")
        (self.source.parent.parent / "Info.plist").write_text("signed metadata fixture")
        self.destination = self.root / "snapshot"
        self.destination.mkdir()

    def copy_command(self, command, **kwargs):
        if command[0] == "/usr/bin/ditto":
            shutil.copytree(command[1], command[2])
        return mock.Mock(returncode=0)

    def test_verified_bundle_layout_and_bound_bytes_are_preserved(self):
        with mock.patch.object(codex_cli_adapter.sys, "platform", "darwin"), mock.patch.object(
            codex_cli_adapter.subprocess, "run", side_effect=self.copy_command
        ) as calls:
            frozen = codex_cli_adapter.snapshot_runtime(
                self.source, self.source.read_bytes(), self.destination
            )
        self.assertEqual(frozen.relative_to(self.destination).as_posix(), "Runtime.app/Contents/MacOS/codex")
        self.assertEqual(frozen.read_bytes(), self.source.read_bytes())
        self.assertTrue((frozen.parent.parent / "Info.plist").is_file())
        self.assertEqual(sum(call.args[0][0] == "/usr/bin/codesign" for call in calls.call_args_list), 2)
        self.assertEqual(frozen.stat().st_mode & 0o777, 0o500)

    def test_replacement_during_bundle_copy_is_rejected(self):
        def copy_then_replace(command, **kwargs):
            result = self.copy_command(command, **kwargs)
            if command[0] == "/usr/bin/ditto":
                (Path(command[2]) / "Contents/MacOS/codex").write_bytes(b"different executable")
            return result
        with mock.patch.object(codex_cli_adapter.sys, "platform", "darwin"), mock.patch.object(
            codex_cli_adapter.subprocess, "run", side_effect=copy_then_replace
        ), self.assertRaises(SystemExit):
            codex_cli_adapter.snapshot_runtime(self.source, self.source.read_bytes(), self.destination)

    def test_invalid_signature_never_reaches_copy_or_execution(self):
        with mock.patch.object(codex_cli_adapter.sys, "platform", "darwin"), mock.patch.object(
            codex_cli_adapter.subprocess, "run", return_value=mock.Mock(returncode=1)
        ) as calls, self.assertRaises(SystemExit):
            codex_cli_adapter.snapshot_runtime(self.source, self.source.read_bytes(), self.destination)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_symlink_and_oversized_bundle_fail_before_vendor_tools(self):
        link = self.source.parent.parent / "outside"
        link.symlink_to(self.root)
        with mock.patch.object(codex_cli_adapter.sys, "platform", "darwin"), mock.patch.object(
            codex_cli_adapter.subprocess, "run"
        ) as calls, self.assertRaises(SystemExit):
            codex_cli_adapter.snapshot_runtime(self.source, self.source.read_bytes(), self.destination)
        calls.assert_not_called()
        link.unlink()
        with mock.patch.object(codex_cli_adapter.sys, "platform", "darwin"), mock.patch.object(
            codex_cli_adapter, "MAX_RUNTIME_BYTES", 1
        ), mock.patch.object(codex_cli_adapter.subprocess, "run") as calls, self.assertRaises(SystemExit):
            codex_cli_adapter.snapshot_runtime(self.source, self.source.read_bytes(), self.destination)
        calls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
