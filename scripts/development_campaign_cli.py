#!/usr/bin/env python3
"""Run or verify a non-qualifying real-model development campaign."""

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

import development_campaign  # noqa: E402
import target_session  # noqa: E402


def load_object(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise development_campaign.DevelopmentCampaignError(
            f"{label} must be a regular non-symlink file"
        )
    if path.stat().st_size > 50 * 1024 * 1024:
        raise development_campaign.DevelopmentCampaignError(
            f"{label} exceeds fifty MiB"
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise development_campaign.DevelopmentCampaignError(
            f"{label} must contain an object"
        )
    return value


def source_state(config: dict) -> tuple[str, bool]:
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
    if commit != config.get("source_commit"):
        raise development_campaign.DevelopmentCampaignError(
            "development config source commit differs from the checkout"
        )
    return commit, not bool(dirty)


def environment(names: list[str]) -> dict[str, str]:
    missing = [name for name in names if name not in os.environ]
    if missing:
        raise development_campaign.DevelopmentCampaignError(
            "required environment variables are unavailable: " + ", ".join(missing)
        )
    return {name: os.environ[name] for name in names}


def write_private_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def command_run(args) -> int:
    suite = load_object(args.suite, "suite")
    target_config = load_object(args.target_config, "target config")
    config = load_object(args.config, "development config")
    _, clean = source_state(config)
    if not clean:
        raise development_campaign.DevelopmentCampaignError(
            "development campaign requires a clean source tree"
        )
    target_environment = environment(target_config["provider"]["environment_allowlist"])
    reviewer_environment = environment(config["reviewer"]["environment_allowlist"])
    target = target_session.FrozenStdioProvider(
        config=target_config,
        adapter_path=args.target_adapter,
        environment=target_environment,
        timeout_seconds=args.timeout,
        clock=lambda: datetime.now(timezone.utc),
    )
    reviewer = development_campaign.FrozenAuxiliaryReviewer(
        config=config,
        suite=suite,
        adapter_path=args.reviewer_adapter,
        environment=reviewer_environment,
        timeout_seconds=args.timeout,
        clock=lambda: datetime.now(timezone.utc),
    )
    try:
        artifact = development_campaign.run_development_campaign(
            suite=suite,
            target_config=target_config,
            development_config=config,
            target_provider=development_campaign.CapturedTargetProvider(target),
            reviewer=reviewer,
            source_tree_clean=True,
            clock=lambda: datetime.now(timezone.utc),
        )
    finally:
        reviewer.close()
        target.close()
    write_private_new(args.output, artifact)
    infrastructure_failures = {
        "PROVIDER_ERROR",
        "GRADER_ERROR",
        "PROVIDER_CONTRACT_ERROR",
        "GRADER_CONTRACT_ERROR",
    }
    execution_complete = not any(
        failure["code"] in infrastructure_failures
        for run in artifact["runs"]
        for failure in run["failures"]
    )
    print(
        json.dumps(
            {
                "status": "pass" if execution_complete else "fail",
                "output": str(args.output),
                "planned_run_count": artifact["planned_run_count"],
                "completed_run_count": artifact["completed_run_count"],
                "automated_pass": artifact["summary"]["automated_pass"],
                "automated_fail": artifact["summary"]["automated_fail"],
                "aggregate_sha256": artifact["aggregate_sha256"],
                "qualification_claim_allowed": False,
            },
            indent=2,
        )
    )
    return 0 if execution_complete else 1


def command_verify(args) -> int:
    artifact = load_object(args.result, "development result")
    errors = development_campaign.result_errors(artifact)
    print(
        json.dumps(
            {"status": "pass" if not errors else "fail", "errors": errors},
            indent=2,
        )
    )
    return 1 if errors else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
    run.add_argument("--target-config", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--target-adapter", type=Path, required=True)
    run.add_argument("--reviewer-adapter", type=Path, required=True)
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--result", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "run":
            return command_run(args)
        if args.command == "verify":
            return command_verify(args)
    except (
        development_campaign.DevelopmentCampaignError,
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
