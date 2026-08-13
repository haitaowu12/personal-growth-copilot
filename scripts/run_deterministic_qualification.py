#!/usr/bin/env python3
"""Run deterministic qualification checks and emit a hash-bound evidence file."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build/evidence/deterministic-qualification.json"
CHECKS = (
    ("repository-validation", ("scripts/validate.py",)),
    ("evidence-rebalancing-design-assets", ("scripts/validate_design_assets.py",)),
    ("evaluation-manifest-lint", ("scripts/lint_eval_manifest.py",)),
    (
        "multiturn-harness-conformance",
        ("evals/run.py", "--conformance", "--require-clean"),
    ),
    ("dependency-consistency", ("-m", "pip", "check")),
    (
        "deterministic-unit-tests",
        ("-m", "unittest", "discover", "-s", "tests", "-v"),
    ),
    (
        "growth-record-example",
        (
            "skill/personal-growth-copilot/scripts/growth_record.py",
            "validate",
            "examples/growth-record.example.json",
        ),
    ),
    (
        "skill-structure-validation",
        (".ci/quick_validate.py", "skill/personal-growth-copilot"),
    ),
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _locked_dependencies() -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for line in (ROOT / "requirements/ci.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)", line)
        if match is None:
            continue
        name, expected = match.groups()
        dependencies.append(
            {
                "name": name,
                "locked": expected,
                "installed": importlib.metadata.version(name),
            }
        )
    return dependencies


def build_evidence() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for check_id, arguments in CHECKS:
        command = [sys.executable, *arguments]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"[{check_id}] exit={completed.returncode}")
        if completed.stdout:
            print(
                completed.stdout,
                end="" if completed.stdout.endswith("\n") else "\n",
            )
        if completed.stderr:
            print(
                completed.stderr,
                file=sys.stderr,
                end="" if completed.stderr.endswith("\n") else "\n",
            )
        results.append(
            {
                "check_id": check_id,
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "stdout_sha256": _sha256(completed.stdout.encode("utf-8")),
                "stderr_sha256": _sha256(completed.stderr.encode("utf-8")),
            }
        )

    dependencies = _locked_dependencies()
    dependency_lock_match = all(
        item["locked"] == item["installed"] for item in dependencies
    )
    source_tree_status = _git_status()
    source_tree_clean = not source_tree_status
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "evidence_type": "deterministic-controls-only",
        "status": (
            "pass"
            if all(item["exit_code"] == 0 for item in results)
            and dependency_lock_match
            and source_tree_clean
            else "fail"
        ),
        "generated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source_commit": _git_commit(),
        "source_tree_clean": source_tree_clean,
        "source_tree_status": source_tree_status,
        "python": sys.version,
        "platform": platform.platform(),
        "requirements_lock_sha256": _sha256(
            (ROOT / "requirements/ci.txt").read_bytes()
        ),
        "dependencies": dependencies,
        "dependency_lock_match": dependency_lock_match,
        "checks": results,
        "claim_limit": (
            "This artifact proves deterministic source, schema, design-asset, "
            "record-store, safety-state, resolver-failure, branchable-harness-"
            "conformance, blinded-review, target-transport, conditional submitted-"
            "matrix aggregation, manifest, qualification-packet-preflight, and "
            "skill-structure checks only. Candidate technique, session-capsule, "
            "comparator, and ordinary-growth assets are structurally validated "
            "but are not integrated target behavior. It is not target-model "
            "behavior, English/Chinese human review, privacy-pilot, efficacy, "
            "or release evidence."
        ),
    }
    aggregate_payload = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    evidence["aggregate_sha256"] = _sha256(aggregate_payload)
    return evidence


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> int:
    args = parser().parse_args()
    evidence = build_evidence()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "output": str(output),
                "aggregate_sha256": evidence["aggregate_sha256"],
            },
            indent=2,
        )
    )
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
