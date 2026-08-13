#!/usr/bin/env python3
"""Build and verify conditional full-suite submitted-matrix evidence."""

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

import campaign  # noqa: E402
import target_session  # noqa: E402


def load_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise campaign.CampaignError(f"input is not a regular file: {path}")
    if path.stat().st_size > 10_485_760:
        raise campaign.CampaignError(f"input exceeds ten MiB: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise campaign.CampaignError(f"input is not an object: {path}")
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
        raise campaign.CampaignError("campaign operation requires a clean source tree")
    if commit != config.get("source_commit"):
        raise campaign.CampaignError(
            "campaign config source_commit differs from the current checkout"
        )


def now() -> datetime:
    return datetime.now(timezone.utc)


def common_inputs(args):
    suite = load_json(args.suite)
    config = load_json(args.config)
    require_clean_source(config)
    if errors := target_session.validate_target_config(config, suite):
        raise campaign.CampaignError("invalid target config: " + "; ".join(errors))
    return suite, config


def command_build_manifest(args) -> int:
    suite, config = common_inputs(args)
    manifest = campaign.build_result_manifest(
        result_paths=args.result,
        manifest_path=args.output,
        suite=suite,
        config=config,
        clock=now,
    )
    write_private_new(args.output, manifest)
    print(
        json.dumps(
            {
                "status": "pass",
                "output": str(args.output),
                "result_count": len(manifest["results"]),
                "manifest_sha256": manifest["manifest_sha256"],
            },
            indent=2,
        )
    )
    return 0


def command_aggregate(args) -> int:
    suite, config = common_inputs(args)
    manifest = load_json(args.manifest)
    artifact = campaign.aggregate_campaign(
        manifest=manifest,
        manifest_path=args.manifest,
        suite=suite,
        config=config,
        clock=now,
    )
    write_private_new(args.output, artifact)
    print(
        json.dumps(
            {
                "status": "pass",
                "output": str(args.output),
                "campaign_behavioral_status": artifact["behavioral_status"],
                "campaign_evidence_status": artifact["evidence_status"],
                "aggregate_sha256": artifact["aggregate_sha256"],
            },
            indent=2,
        )
    )
    return 0


def command_verify(args) -> int:
    suite, config = common_inputs(args)
    manifest = load_json(args.manifest)
    artifact = load_json(args.result)
    errors = campaign.campaign_result_errors(
        artifact,
        manifest=manifest,
        manifest_path=args.manifest,
        suite=suite,
        config=config,
        clock=now,
    )
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    def common(command):
        command.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
        command.add_argument("--config", type=Path, required=True)

    build = commands.add_parser("build-manifest")
    common(build)
    build.add_argument("--result", type=Path, action="append", required=True)
    build.add_argument("--output", type=Path, required=True)

    aggregate = commands.add_parser("aggregate")
    common(aggregate)
    aggregate.add_argument("--manifest", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    common(verify)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--result", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "build-manifest":
            return command_build_manifest(args)
        if args.command == "aggregate":
            return command_aggregate(args)
        if args.command == "verify":
            return command_verify(args)
    except (
        campaign.CampaignError,
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
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
