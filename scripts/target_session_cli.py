#!/usr/bin/env python3
"""Operate immutable Personal Growth Copilot target-evaluation session steps."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import target_session  # noqa: E402


def load_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise target_session.TargetEvaluationError(f"input is not a regular file: {path}")
    if path.stat().st_size > 10_485_760:
        raise target_session.TargetEvaluationError(f"input exceeds ten MiB: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise target_session.TargetEvaluationError(f"input is not an object: {path}")
    return value


def write_private_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def require_clean_source(config: dict) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise target_session.TargetEvaluationError(
            "target execution requires a clean source tree"
        )
    if commit != config.get("source_commit"):
        raise target_session.TargetEvaluationError(
            "target config source_commit differs from the current checkout"
        )


def now() -> datetime:
    return datetime.now(timezone.utc)


def restore(args):
    suite = load_json(args.suite)
    config = load_json(args.config)
    require_clean_source(config)
    artifact = load_json(args.session)
    session = target_session.TargetSession.from_artifact(
        suite=suite,
        config=config,
        artifact=artifact,
        clock=now,
    )
    return suite, config, session


def command_init(args) -> int:
    suite = load_json(args.suite)
    config = load_json(args.config)
    require_clean_source(config)
    session = target_session.TargetSession(
        suite=suite,
        config=config,
        case_id=args.case_id,
        system_id=args.system_id,
        variant_id=args.variant_id,
        repetition=args.repetition,
        clock=now,
    )
    write_private_new(args.output, session.to_artifact())
    return 0


def command_capture(args) -> int:
    _, config, session = restore(args)
    environment = {}
    for name in args.env:
        if name not in os.environ:
            raise target_session.ProviderProtocolError(
                f"allowlisted environment variable is unavailable: {name}"
            )
        environment[name] = os.environ[name]
    provider = target_session.FrozenStdioProvider(
        config=config,
        adapter_path=args.adapter,
        environment=environment,
        timeout_seconds=args.timeout,
        clock=now,
    )
    try:
        session.capture(provider)
    finally:
        provider.close()
    write_private_new(args.output, session.to_artifact())
    return 0


def command_import_review(args) -> int:
    _, _, session = restore(args)
    review = load_json(args.review)
    session.import_review(review)
    write_private_new(args.output, session.to_artifact())
    return 0


def command_export_review_request(args) -> int:
    _, _, session = restore(args)
    write_private_new(args.output, session.review_request())
    return 0


def command_finalize(args) -> int:
    suite, config, session = restore(args)
    result = target_session.finalize_session(session)
    if not target_session.verify_target_result(
        result, suite=suite, config=config, clock=now
    ):
        raise target_session.TargetEvaluationError(
            "final target result failed deterministic replay verification"
        )
    write_private_new(args.output, result)
    return 0


def command_verify(args) -> int:
    suite = load_json(args.suite)
    config = load_json(args.config)
    require_clean_source(config)
    result = load_json(args.result)
    errors = target_session.target_result_errors(
        result, suite=suite, config=config, clock=now
    )
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)

    def common(command):
        command.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
        command.add_argument("--config", type=Path, required=True)

    initialize = subcommands.add_parser("init")
    common(initialize)
    initialize.add_argument("--case-id", required=True)
    initialize.add_argument(
        "--system-id",
        required=True,
        choices=["target", "direct_assistant", "structured_reflection"],
    )
    initialize.add_argument("--variant-id", default="canonical")
    initialize.add_argument("--repetition", type=int, default=1)
    initialize.add_argument("--output", type=Path, required=True)

    capture = subcommands.add_parser("capture")
    common(capture)
    capture.add_argument("--session", type=Path, required=True)
    capture.add_argument("--adapter", type=Path, required=True)
    capture.add_argument("--env", action="append", default=[])
    capture.add_argument("--timeout", type=int, default=120)
    capture.add_argument("--output", type=Path, required=True)

    import_review = subcommands.add_parser("import-review")
    common(import_review)
    import_review.add_argument("--session", type=Path, required=True)
    import_review.add_argument("--review", type=Path, required=True)
    import_review.add_argument("--output", type=Path, required=True)

    export_review = subcommands.add_parser("export-review-request")
    common(export_review)
    export_review.add_argument("--session", type=Path, required=True)
    export_review.add_argument("--output", type=Path, required=True)

    finalize = subcommands.add_parser("finalize")
    common(finalize)
    finalize.add_argument("--session", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)

    verify = subcommands.add_parser("verify")
    common(verify)
    verify.add_argument("--result", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            return command_init(args)
        if args.command == "capture":
            return command_capture(args)
        if args.command == "import-review":
            return command_import_review(args)
        if args.command == "export-review-request":
            return command_export_review_request(args)
        if args.command == "finalize":
            return command_finalize(args)
        if args.command == "verify":
            return command_verify(args)
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        target_session.TargetEvaluationError,
    ) as exc:
        print(
            json.dumps(
                {"status": "fail", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
