#!/usr/bin/env python3
"""Create a release manifest only from a current, fully verified PROMOTED index."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402

SCHEMA = ROOT / "release/verified-release-manifest.schema.json"


class ReleaseApplicationError(RuntimeError):
    pass


def source_identity() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        raise ReleaseApplicationError("release application requires a clean source tree")
    return commit


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReleaseApplicationError("release clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_manifest(
    *,
    index_path: Path,
    policy_path: Path,
    expected_commit: str,
    expected_policy_sha256: str,
    expected_index_sha256: str,
    release: str,
    generated_at: datetime,
    verifier: Callable[..., dict[str, Any]] = release_evidence.verify,
) -> dict[str, Any]:
    result = verifier(
        index_path=index_path,
        policy_path=policy_path,
        expected_commit=expected_commit,
        expected_policy_sha256=expected_policy_sha256,
        expected_index_sha256=expected_index_sha256,
    )
    if result.get("verification_status") != "pass":
        raise ReleaseApplicationError(
            "release evidence verification failed: " + "; ".join(result.get("errors", []))
        )
    if (
        result.get("release_status") != "PROMOTED"
        or result.get("qualification_update_allowed") is not True
        or result.get("verified_gate_count") != len(release_evidence.GATES)
    ):
        raise ReleaseApplicationError("current evidence index does not authorize promotion")
    if result.get("candidate_commit") != expected_commit:
        raise ReleaseApplicationError("verification result binds another candidate")
    manifest = {
        "schema_version": "1.0",
        "evidence_class": "verified-release-manifest",
        "status": "PROMOTED",
        "candidate_commit": expected_commit,
        "release": release,
        "generated_at": timestamp(generated_at),
        "trust_policy_sha256": expected_policy_sha256,
        "evidence_index_sha256": expected_index_sha256,
        "verified_gate_count": len(release_evidence.GATES),
        "qualification_update_allowed": True,
        "claim": "production-promotion-authorized-by-current-verified-evidence",
    }
    manifest["manifest_sha256"] = release_evidence.digest(manifest)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(manifest)
    )
    if errors:
        raise ReleaseApplicationError("verified release manifest failed its schema")
    return manifest


def write_private_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ReleaseApplicationError("verified release output is create-only")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--expected-policy-sha256", required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--release", default=(ROOT / "VERSION").read_text().strip())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = source_identity()
        manifest = build_manifest(
            index_path=args.index,
            policy_path=args.policy,
            expected_commit=candidate,
            expected_policy_sha256=args.expected_policy_sha256,
            expected_index_sha256=args.expected_index_sha256,
            release=args.release,
            generated_at=datetime.now(timezone.utc),
        )
        write_private_new(args.output, manifest)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "manifest_sha256": manifest["manifest_sha256"],
                    "release_status": "PROMOTED",
                },
                indent=2,
            )
        )
        return 0
    except (
        OSError,
        subprocess.SubprocessError,
        ReleaseApplicationError,
        release_evidence.ReleaseEvidenceError,
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
