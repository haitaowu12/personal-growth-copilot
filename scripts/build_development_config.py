#!/usr/bin/env python3
"""Build a bounded real-model development campaign configuration."""

from __future__ import annotations

import argparse
import hashlib
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


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def source_identity() -> str:
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
        raise ValueError("development freeze requires a clean source tree")
    return commit


def write_private_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_config(
    *,
    suite: dict,
    target_config: dict,
    source_commit: str,
    reviewer_adapter: Path,
    reviewer_adapter_version: str,
    runtime_executable: Path,
    reviewer_model: str,
    reviewer_model_version: str,
    reviewer_settings: dict,
    case_ids: list[str],
    systems: list[str],
    max_turns: int,
    frozen_at: datetime,
) -> dict:
    if reviewer_adapter.is_symlink():
        raise ValueError("review adapter must not be a symlink")
    reviewer_adapter = reviewer_adapter.resolve(strict=True)
    if not reviewer_adapter.is_file() or not os.access(reviewer_adapter, os.X_OK):
        raise ValueError("review adapter must be an executable regular file")
    if runtime_executable.is_symlink():
        raise ValueError("review runtime executable must not be a symlink")
    runtime_executable = runtime_executable.resolve(strict=True)
    if not runtime_executable.is_file() or not os.access(runtime_executable, os.X_OK):
        raise ValueError("review runtime executable must be an executable regular file")
    if target_session._contains_sensitive_key(reviewer_settings):
        raise ValueError("reviewer settings contain a secret-like key")
    config = {
        "schema_version": "1.0",
        "mode": "model-assisted-development",
        "qualification_claim_allowed": False,
        "source_commit": source_commit,
        "frozen_at": development_campaign.timestamp(frozen_at),
        "suite_sha256": development_campaign.digest(suite),
        "target_config_sha256": development_campaign.digest(target_config),
        "systems": systems,
        "case_ids": case_ids,
        "run_plan": development_campaign.expected_plan(suite, case_ids, systems),
        "max_turns": max_turns,
        "reviewer": {
            "protocol": development_campaign.REVIEW_PROTOCOL,
            "adapter_version": reviewer_adapter_version,
            "adapter_sha256": file_hash(reviewer_adapter),
            "runtime_executable_sha256": file_hash(runtime_executable),
            "output_schema_sha256": development_campaign.digest(
                json.loads(
                    development_campaign.REVIEW_OUTPUT_SCHEMA.read_text(
                        encoding="utf-8"
                    )
                )
            ),
            "rubric_sha256": file_hash(development_campaign.RUBRIC_PATH),
            "host": "codex-cli",
            "model": reviewer_model,
            "model_version": reviewer_model_version,
            "settings": reviewer_settings,
            "tool_permissions": [],
            "environment_allowlist": [
                "PGC_CODEX_AUTH_ROOT",
                "PGC_CODEX_BIN",
            ],
        },
    }
    if errors := development_campaign.validate_development_config(
        config, suite, target_config
    ):
        raise ValueError("; ".join(errors))
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-config", type=Path, required=True)
    parser.add_argument("--reviewer-adapter", type=Path, required=True)
    parser.add_argument("--reviewer-adapter-version", required=True)
    parser.add_argument("--runtime-executable", type=Path, required=True)
    parser.add_argument("--reviewer-model", required=True)
    parser.add_argument("--reviewer-model-version", required=True)
    parser.add_argument("--reviewer-settings-file", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--system-id", action="append", default=[])
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        suite = load_object(ROOT / "evals/cases.json", "suite")
        target_config = load_object(args.target_config, "target config")
        commit = source_identity()
        if target_config.get("source_commit") != commit:
            raise ValueError("target config is not bound to the current clean commit")
        settings = load_object(args.reviewer_settings_file, "reviewer settings")
        canonical_cases = [item["id"] for item in suite["cases"]]
        requested_cases = set(args.case_id or canonical_cases)
        if unknown := requested_cases - set(canonical_cases):
            raise ValueError(f"unknown development cases: {sorted(unknown)}")
        case_ids = [item for item in canonical_cases if item in requested_cases]
        canonical_systems = list(target_session.system_profiles.SYSTEM_IDS)
        requested_systems = set(args.system_id or canonical_systems)
        if unknown := requested_systems - set(canonical_systems):
            raise ValueError(f"unknown development systems: {sorted(unknown)}")
        systems = [item for item in canonical_systems if item in requested_systems]
        config = build_config(
            suite=suite,
            target_config=target_config,
            source_commit=commit,
            reviewer_adapter=args.reviewer_adapter,
            reviewer_adapter_version=args.reviewer_adapter_version,
            runtime_executable=args.runtime_executable,
            reviewer_model=args.reviewer_model,
            reviewer_model_version=args.reviewer_model_version,
            reviewer_settings=settings,
            case_ids=case_ids,
            systems=systems,
            max_turns=args.max_turns,
            frozen_at=datetime.now(timezone.utc),
        )
        write_private_new(args.output, config)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "config_sha256": development_campaign.digest(config),
                    "planned_run_count": len(config["run_plan"]),
                },
                indent=2,
            )
        )
        return 0
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"status": "fail", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
