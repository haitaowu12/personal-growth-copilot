#!/usr/bin/env python3
"""Initialize and inspect an exact, resumable authored-evaluation workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "scripts"))

import host_privacy_discovery  # noqa: E402
import target_session  # noqa: E402

WORKSPACE_SCHEMA = ROOT / "release/campaign-workspace.schema.json"
STATUS_SCHEMA = ROOT / "release/campaign-workspace-status.schema.json"


class CampaignWorkspaceError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CampaignWorkspaceError("workspace clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CampaignWorkspaceError(f"{label} must be a regular non-symlink file")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise CampaignWorkspaceError(f"{label} exceeds fifty MiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CampaignWorkspaceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CampaignWorkspaceError(f"{label} must contain an object")
    return value


def schema_errors(value: object, path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def source_state(config: dict[str, Any]) -> tuple[str, bool]:
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
    if commit != config.get("source_commit"):
        raise CampaignWorkspaceError("target config differs from the clean checkout")
    return commit, not bool(dirty)


def run_slug(identity: dict[str, Any]) -> str:
    return "run-" + digest({"domain": "pgc-workspace-run-v1", **identity})[:24]


def _relative(path: Path, root: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve()).as_posix()


def write_private_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise CampaignWorkspaceError(f"create-only output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def initialize_workspace(
    *,
    workspace_root: Path,
    config_path: Path,
    output: Path,
    suite_path: Path = ROOT / "evals/cases.json",
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    source_checker: Callable[[dict[str, Any]], tuple[str, bool]] = source_state,
) -> dict[str, Any]:
    config = load_object(config_path, "target config")
    suite = load_object(suite_path, "target suite")
    if errors := target_session.validate_target_config(config, suite):
        raise CampaignWorkspaceError("invalid target config: " + "; ".join(errors))
    candidate, clean = source_checker(config)
    if not clean:
        raise CampaignWorkspaceError("workspace initialization requires a clean tree")
    if workspace_root.exists() or workspace_root.is_symlink():
        raise CampaignWorkspaceError("workspace initialization is create-only")
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(workspace_root, 0o700)
    os.chmod(workspace_root, 0o700)
    try:
        runs_root = workspace_root / "runs"
        os.mkdir(runs_root, 0o700)
        os.chmod(runs_root, 0o700)
        config_snapshot = workspace_root / "target-config.json"
        write_private_new(config_snapshot, config)
        entries = []
        for ordinal, identity in enumerate(config["run_plan"], start=1):
            slug = run_slug(identity)
            directory = runs_root / slug
            os.mkdir(directory, 0o700)
            os.chmod(directory, 0o700)
            session = target_session.TargetSession(
                suite=suite,
                config=config,
                case_id=identity["case_id"],
                system_id=identity["system_id"],
                variant_id=identity["variant_id"],
                repetition=identity["repetition"],
                clock=clock,
            )
            write_private_new(directory / "session-000.json", session.to_artifact())
            entries.append(
                {
                    "ordinal": ordinal,
                    "run_slug": slug,
                    "identity": identity,
                    "directory": f"runs/{slug}",
                }
            )
        workspace = {
            "schema_version": "1.0",
            "evidence_class": "authored-campaign-workspace",
            "qualification_claim_allowed": False,
            "candidate_commit": candidate,
            "created_at": timestamp(clock()),
            "workspace_root_sha256": host_privacy_discovery.path_identity(
                workspace_root
            ),
            "config_path": "target-config.json",
            "config_sha256": hashlib.sha256(
                config_snapshot.read_bytes()
            ).hexdigest(),
            "suite_sha256": target_session._digest(suite),
            "run_plan_sha256": target_session._digest(config["run_plan"]),
            "run_count": len(entries),
            "runs": entries,
        }
        workspace["workspace_sha256"] = digest(workspace)
        if errors := schema_errors(workspace, WORKSPACE_SCHEMA):
            raise CampaignWorkspaceError(
                "workspace schema failure: " + "; ".join(errors)
            )
        if output.parent.resolve() != workspace_root.resolve():
            raise CampaignWorkspaceError("workspace manifest must be written at the workspace root")
        write_private_new(output, workspace)
        return workspace
    except Exception:
        # Preserve nothing from a failed initialization.
        for path in sorted(workspace_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        workspace_root.rmdir()
        raise


def _latest_session(run_directory: Path) -> Path | None:
    candidates = sorted(run_directory.glob("session-[0-9][0-9][0-9].json"))
    return candidates[-1] if candidates else None


def _next_session_path(run_directory: Path, latest: Path) -> Path:
    number = int(latest.stem.split("-")[-1]) + 1
    return run_directory / f"session-{number:03d}.json"


def workspace_status(
    *,
    workspace_path: Path,
    suite_path: Path = ROOT / "evals/cases.json",
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    workspace = load_object(workspace_path, "workspace manifest")
    if errors := schema_errors(workspace, WORKSPACE_SCHEMA):
        raise CampaignWorkspaceError("invalid workspace: " + "; ".join(errors))
    if workspace["workspace_sha256"] != digest(
        {key: value for key, value in workspace.items() if key != "workspace_sha256"}
    ):
        raise CampaignWorkspaceError("workspace self-hash mismatch")
    root = workspace_path.parent.resolve()
    if host_privacy_discovery.path_identity(root) != workspace["workspace_root_sha256"]:
        raise CampaignWorkspaceError("workspace root object identity changed")
    config_path = (root / workspace["config_path"]).resolve(strict=True)
    config = load_object(config_path, "target config")
    suite = load_object(suite_path, "target suite")
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != workspace["config_sha256"]:
        raise CampaignWorkspaceError("workspace target-config hash mismatch")
    statuses = []
    counts: Counter[str] = Counter()
    for entry in workspace["runs"]:
        run_directory = root / entry["directory"]
        errors: list[str] = []
        latest = _latest_session(run_directory)
        request_path = run_directory / "review-request.json"
        response_path = run_directory / "review-response.json"
        result_path = run_directory / "result.json"
        status = "INVALID"
        action = "REPAIR"
        command: str | None = None
        session = None
        if result_path.is_file() and not result_path.is_symlink():
            result = load_object(result_path, "target result")
            result_errors = target_session.target_result_errors(
                result, suite=suite, config=config, clock=clock
            )
            if result_errors:
                errors.extend(result_errors)
            else:
                status, action = "FINALIZED", "NONE"
        elif latest is None:
            status, action = "UNINITIALIZED", "INIT"
            command = (
                f"python scripts/target_session_cli.py init --config {config_path} "
                f"--case-id {entry['identity']['case_id']} --system-id {entry['identity']['system_id']} "
                f"--variant-id {entry['identity']['variant_id']} --repetition {entry['identity']['repetition']} "
                f"--output {run_directory / 'session-000.json'}"
            )
        else:
            try:
                artifact = load_object(latest, "target session")
                session = target_session.TargetSession.from_artifact(
                    suite=suite, config=config, artifact=artifact, clock=clock
                )
            except (target_session.TargetEvaluationError, CampaignWorkspaceError) as exc:
                errors.append(str(exc))
            if session is not None:
                next_session = _next_session_path(run_directory, latest)
                if session.status == "AWAITING_PROVIDER":
                    status, action = "AWAITING_PROVIDER", "CAPTURE"
                    command = (
                        f"python scripts/target_session_cli.py capture --config {config_path} "
                        f"--session {latest} --adapter providers/codex_cli_adapter.py "
                        f"--env PGC_EVAL_REPO_ROOT --env PGC_CODEX_BIN --env PGC_CODEX_AUTH_ROOT "
                        f"--output {next_session}"
                    )
                elif session.status == "AWAITING_HUMAN_REVIEW":
                    if not request_path.exists():
                        status, action = "AWAITING_REVIEW_EXPORT", "EXPORT_REVIEW"
                        command = (
                            f"python scripts/target_session_cli.py export-review-request "
                            f"--config {config_path} --session {latest} --output {request_path}"
                        )
                    elif response_path.is_file() and not response_path.is_symlink():
                        status, action = "READY_TO_IMPORT_REVIEW", "IMPORT_REVIEW"
                        command = (
                            f"python scripts/target_session_cli.py import-review --config {config_path} "
                            f"--session {latest} --review {response_path} --output {next_session}"
                        )
                    else:
                        status, action = "AWAITING_EXTERNAL_REVIEW", "WAIT_FOR_REVIEW"
                elif session.status == "COMPLETE":
                    status, action = "READY_TO_FINALIZE", "FINALIZE"
                    command = (
                        f"python scripts/target_session_cli.py finalize --config {config_path} "
                        f"--session {latest} --output {result_path}"
                    )
                else:
                    errors.append(f"unsupported target session status: {session.status}")
        if errors:
            status, action, command = "INVALID", "REPAIR", None
        counts[status] += 1
        statuses.append(
            {
                "ordinal": entry["ordinal"],
                "run_slug": entry["run_slug"],
                "identity": entry["identity"],
                "status": status,
                "latest_session_path": _relative(latest, root) if latest else None,
                "review_request_path": _relative(request_path, root) if request_path.exists() else None,
                "review_response_path": _relative(response_path, root) if response_path.exists() else None,
                "result_path": _relative(result_path, root) if result_path.exists() else None,
                "next_action": action,
                "next_command": command,
                "errors": errors,
            }
        )
    report = {
        "schema_version": "1.0",
        "evidence_class": "authored-campaign-workspace-status",
        "qualification_claim_allowed": False,
        "candidate_commit": workspace["candidate_commit"],
        "generated_at": timestamp(clock()),
        "workspace_sha256": workspace["workspace_sha256"],
        "run_count": len(statuses),
        "counts": dict(sorted(counts.items())),
        "runs": statuses,
        "complete": counts.get("FINALIZED", 0) == len(statuses),
    }
    report["status_sha256"] = digest(report)
    if errors := schema_errors(report, STATUS_SCHEMA):
        raise CampaignWorkspaceError(
            "workspace status schema failure: " + "; ".join(errors)
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--workspace-root", type=Path, required=True)
    initialize.add_argument("--config", type=Path, required=True)
    initialize.add_argument("--output", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--workspace", type=Path, required=True)
    status.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize_workspace(
                workspace_root=args.workspace_root,
                config_path=args.config,
                output=args.output,
            )
        else:
            result = workspace_status(workspace_path=args.workspace)
            if args.output:
                write_private_new(args.output, result)
        print(json.dumps(result, indent=2))
        return 0
    except (
        CampaignWorkspaceError,
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
