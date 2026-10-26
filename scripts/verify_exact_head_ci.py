#!/usr/bin/env python3
"""Bind a passing deterministic qualification receipt to the hosted checkout SHA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "release/exact-head-ci.schema.json"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_report(
    *,
    qualification_path: Path,
    expected_sha: str,
    checkout_sha: str,
    workflow_ref: str,
    generated_at: datetime,
) -> dict:
    if not all(
        isinstance(value, str)
        and len(value) == 40
        and set(value) <= set("0123456789abcdef")
        for value in (expected_sha, checkout_sha)
    ):
        raise ValueError("expected and checkout SHA values must be forty lowercase hex characters")
    data = qualification_path.read_bytes()
    receipt = json.loads(data.decode("utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("qualification receipt must contain an object")
    if receipt.get("status") != "pass":
        raise ValueError("qualification receipt is not passing")
    if receipt.get("source_tree_clean") is not True:
        raise ValueError("qualification receipt does not bind a clean source tree")
    if receipt.get("source_commit") != checkout_sha or checkout_sha != expected_sha:
        raise ValueError("qualification, checkout, and expected SHA values differ")
    aggregate = receipt.get("aggregate_sha256")
    if not isinstance(aggregate, str) or len(aggregate) != 64:
        raise ValueError("qualification aggregate hash is absent")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone aware")
    report = {
        "schema_version": "1.0",
        "evidence_class": "hosted-exact-head-ci",
        "status": "PASS",
        "expected_sha": expected_sha,
        "checkout_sha": checkout_sha,
        "qualification_source_commit": receipt["source_commit"],
        "qualification_sha256": hashlib.sha256(data).hexdigest(),
        "qualification_aggregate_sha256": aggregate,
        "source_tree_clean": True,
        "generated_at": generated_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "workflow_ref": workflow_ref,
    }
    report["report_sha256"] = digest(report)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(report)
    )
    if errors:
        raise ValueError("exact-head report failed its schema")
    return report


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--workflow-ref",
        default=os.environ.get("GITHUB_WORKFLOW_REF", "local-exact-head-check"),
    )
    args = parser.parse_args()
    try:
        checkout = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        report = build_report(
            qualification_path=args.qualification,
            expected_sha=args.expected_sha,
            checkout_sha=checkout,
            workflow_ref=args.workflow_ref,
            generated_at=datetime.now(timezone.utc),
        )
        write_new(args.output, report)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "report_sha256": report["report_sha256"],
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
