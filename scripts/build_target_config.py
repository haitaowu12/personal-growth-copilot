#!/usr/bin/env python3
"""Build a secret-free, exact-source target-evaluation freeze configuration."""

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

import target_session  # noqa: E402

SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "authorization",
    "cookie",
    "bearer",
    "client_secret",
    "access_key",
    "signing_key",
)
SENSITIVE_EXACT_KEYS = {"auth", "headers", "session"}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_sensitive_keys(value, path="settings") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_EXACT_KEYS or any(
                fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS
            ):
                raise ValueError(f"{path}.{key}: secret-like settings keys are prohibited")
            reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_keys(child, f"{path}[{index}]")


def source_identity() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise ValueError("target freeze requires a clean source tree")
    return commit


def write_private_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--adapter-version", required=True)
    parser.add_argument(
        "--runtime-executable",
        type=Path,
        required=True,
        help="Exact inference executable invoked by the adapter (for example, codex)",
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--settings-file", type=Path, required=True)
    parser.add_argument("--reviewer-roster-file", type=Path, required=True)
    parser.add_argument("--tool-permission", action="append", default=[])
    parser.add_argument("--environment-name", action="append", default=[])
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.adapter.is_symlink():
            raise ValueError("adapter must not be a symlink")
        adapter = args.adapter.resolve()
        if not adapter.is_file() or not os.access(adapter, os.X_OK):
            raise ValueError("adapter must be an executable regular non-symlink file")
        if args.runtime_executable.is_symlink():
            raise ValueError("runtime executable must not be a symlink")
        runtime_executable = args.runtime_executable.resolve()
        if not runtime_executable.is_file() or not os.access(runtime_executable, os.X_OK):
            raise ValueError(
                "runtime executable must be an executable regular non-symlink file"
            )
        if args.settings_file.is_symlink() or not args.settings_file.is_file():
            raise ValueError("settings file must be a regular non-symlink file")
        settings = json.loads(args.settings_file.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            raise ValueError("settings file must contain an object")
        reject_sensitive_keys(settings)
        if args.reviewer_roster_file.is_symlink() or not args.reviewer_roster_file.is_file():
            raise ValueError("reviewer roster must be a regular non-symlink file")
        roster_document = json.loads(
            args.reviewer_roster_file.read_text(encoding="utf-8")
        )
        if not isinstance(roster_document, dict) or set(roster_document) != {"reviewers"}:
            raise ValueError("reviewer roster file must contain only a reviewers array")
        reviewer_roster = roster_document["reviewers"]
        suite = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
        case_ids = args.case_id or [case["id"] for case in suite["cases"]]
        systems = ["target", "direct_assistant", "structured_reflection"]
        config = {
            "schema_version": "1.0",
            "mode": "authored-target",
            "source_commit": source_identity(),
            "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "suite_sha256": target_session._digest(suite),
            "baseline_sha256": {
                name: file_hash(path) for name, path in target_session.BASELINES.items()
            },
            "systems": systems,
            "provider": {
                "adapter_protocol": "pgc-stdio-v2",
                "adapter_version": args.adapter_version,
                "adapter_sha256": file_hash(adapter),
                "runtime_executable_sha256": file_hash(runtime_executable),
                "host": args.host,
                "model": args.model,
                "model_version": args.model_version,
                "settings": settings,
                "tool_permissions": sorted(set(args.tool_permission)),
                "environment_allowlist": sorted(set(args.environment_name)),
                "skill_sha256": file_hash(
                    ROOT / "skill/personal-growth-copilot/SKILL.md"
                ),
                "profile_bundle_sha256": target_session.profile_bundle_sha256(),
            },
            "review": {
                "rubric_sha256": file_hash(ROOT / "evals/rubric.md"),
                "calibration_protocol_sha256": file_hash(
                    ROOT / "evals/reviewer-calibration.md"
                ),
                "minimum_reviewers": 2,
                "system_blinding_required": True,
                "chinese_fluency_required": True,
                "agreement_method": "weighted_kappa",
                "agreement_threshold": 0.70,
                "minimum_dimension_score": 3.0,
                "minimum_overall_score": 3.5,
                "identity_verification": "external_pending",
                "reviewer_roster": reviewer_roster,
            },
            "case_ids": case_ids,
            "run_plan": target_session.expected_run_plan(suite, case_ids, systems),
        }
        if errors := target_session.validate_target_config(config, suite):
            raise ValueError("; ".join(errors))
        write_private_new(args.output, config)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "source_commit": config["source_commit"],
                    "config_sha256": target_session._digest(config),
                    "case_count": len(case_ids),
                    "planned_run_count": len(config["run_plan"]),
                },
                indent=2,
            )
        )
        return 0
    except (json.JSONDecodeError, OSError, subprocess.SubprocessError, ValueError) as exc:
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
