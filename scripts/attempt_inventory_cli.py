#!/usr/bin/env python3
"""Capture and verify an externally witnessed target-execution inventory."""

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

import attempt_inventory  # noqa: E402
import campaign  # noqa: E402
import target_session  # noqa: E402


def now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, label: str) -> dict:
    return attempt_inventory._json_object(
        attempt_inventory._read_once(path), label
    )


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
        raise attempt_inventory.AttemptInventoryError(
            "attempt execution requires a clean source tree"
        )
    if commit != config.get("source_commit"):
        raise attempt_inventory.AttemptInventoryError(
            "target config source_commit differs from the current checkout"
        )


def require_full_config(config: dict, suite: dict) -> None:
    if errors := target_session.validate_target_config(config, suite):
        raise attempt_inventory.AttemptInventoryError(
            "invalid target config: " + "; ".join(errors)
        )
    try:
        campaign._require_full_suite_scope(suite, config)
    except campaign.CampaignError as exc:
        raise attempt_inventory.AttemptInventoryError(str(exc)) from exc


def packet_paths(packet_directory: Path, sequence: int) -> tuple[Path, Path, Path]:
    root = packet_directory.resolve() / "attempt-ledger"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return (
        root / f"event-{sequence:06d}.json",
        root / f"receipt-{sequence:06d}.json",
        root / f"index-{sequence:06d}.json",
    )


def prior_sequence(prior_index: Path | None) -> int:
    if prior_index is None:
        return 0
    index = load_json(prior_index, "prior attempt index")
    if errors := attempt_inventory._schema_errors(
        index, attempt_inventory.ATTEMPT_INDEX_SCHEMA
    ):
        raise attempt_inventory.AttemptInventoryError(
            "invalid prior attempt index: " + "; ".join(errors)
        )
    return len(index["entries"])


def append_event(
    args: argparse.Namespace,
    *,
    config: dict,
    event_type: str,
    payload: dict,
    prior_index: Path | None,
) -> tuple[dict, Path]:
    sequence = prior_sequence(prior_index)
    event_path, receipt_path, index_path = packet_paths(
        args.packet_directory, sequence
    )
    index = attempt_inventory.append_witnessed_event(
        config=config,
        campaign_id=args.campaign_id,
        prior_index_path=prior_index,
        event_type=event_type,
        payload=payload,
        witness_adapter=args.witness_adapter,
        policy_path=args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
        event_output=event_path,
        receipt_output=receipt_path,
        index_output=index_path,
        clock=now,
    )
    return index, index_path


def report_index(index: dict, path: Path, *, status: str = "pass") -> None:
    print(
        json.dumps(
            {
                "status": status,
                "latest_index": str(path),
                "index_sha256": index["index_sha256"],
                "event_count": len(index["entries"]),
                "witness_head_sha256": index["entries"][-1]["event_sha256"],
            },
            indent=2,
        )
    )


def common_inputs(args: argparse.Namespace) -> tuple[dict, dict]:
    suite = load_json(args.suite, "target suite")
    config = load_json(args.config, "target config")
    require_clean_source(config)
    require_full_config(config, suite)
    return suite, config


def command_register(args: argparse.Namespace) -> int:
    _, config = common_inputs(args)
    index, path = append_event(
        args,
        config=config,
        event_type="CAMPAIGN_REGISTERED",
        payload={
            "kind": "CAMPAIGN_REGISTERED",
            "planned_run_count": len(config["run_plan"]),
        },
        prior_index=None,
    )
    report_index(index, path)
    return 0


def _restore_session(args: argparse.Namespace, suite: dict, config: dict):
    artifact = load_json(args.session, "target session")
    session = target_session.TargetSession.from_artifact(
        suite=suite,
        config=config,
        artifact=artifact,
        clock=now,
    )
    if session.status != "AWAITING_PROVIDER":
        raise attempt_inventory.AttemptInventoryError(
            "witnessed capture requires a session awaiting the provider"
        )
    return artifact, session


def _capture_finished(
    args: argparse.Namespace,
    *,
    config: dict,
    prior_index: Path,
    attempt_id: str,
    outcome: str,
    completion_sha256: str | None,
    provider_response_id: str | None,
    failure_code: str | None,
) -> tuple[dict, Path]:
    return append_event(
        args,
        config=config,
        event_type="CAPTURE_FINISHED",
        payload={
            "kind": "CAPTURE_FINISHED",
            "attempt_id": attempt_id,
            "outcome": outcome,
            "completion_sha256": completion_sha256,
            "provider_response_id": provider_response_id,
            "failure_code": failure_code,
        },
        prior_index=prior_index,
    )


def command_capture(args: argparse.Namespace) -> int:
    suite, config = common_inputs(args)
    artifact, session = _restore_session(args, suite, config)
    if args.session_output.exists() or args.session_output.is_symlink():
        raise attempt_inventory.AttemptInventoryError(
            "session output is create-only and already exists"
        )
    environment = {}
    for name in args.env:
        if name not in os.environ:
            raise attempt_inventory.AttemptInventoryError(
                f"allowlisted environment variable is unavailable: {name}"
            )
        environment[name] = os.environ[name]
    request = session.pending_request()
    attempt_id = "attempt-" + os.urandom(16).hex()
    identity = {
        "case_id": request.case_id,
        "system_id": request.system_id,
        "variant_id": request.variant_id,
        "repetition": request.repetition,
    }
    _, started_index_path = append_event(
        args,
        config=config,
        event_type="CAPTURE_STARTED",
        payload={
            "kind": "CAPTURE_STARTED",
            "attempt_id": attempt_id,
            "run_identity": identity,
            "turn_id": request.turn_id,
            "session_before_sha256": target_session._digest(artifact),
            "request_sha256": target_session._digest(
                target_session.FrozenStdioProvider.request_payload(request, config)
            ),
        },
        prior_index=args.prior_index,
    )
    provider = None
    try:
        provider = target_session.FrozenStdioProvider(
            config=config,
            adapter_path=args.adapter,
            environment=environment,
            timeout_seconds=args.timeout,
            clock=now,
        )
        completion = session.capture(provider)
    except KeyboardInterrupt:
        _capture_finished(
            args,
            config=config,
            prior_index=started_index_path,
            attempt_id=attempt_id,
            outcome="ABORTED",
            completion_sha256=None,
            provider_response_id=None,
            failure_code="OPERATOR_ABORT",
        )
        raise attempt_inventory.AttemptInventoryError(
            "provider capture was aborted and recorded"
        )
    except Exception as exc:
        failure_code = (
            "PROVIDER_ERROR"
            if isinstance(exc, target_session.ProviderProtocolError)
            else "HOST_FAILURE"
        )
        failed_index, failed_path = _capture_finished(
            args,
            config=config,
            prior_index=started_index_path,
            attempt_id=attempt_id,
            outcome="FAILURE",
            completion_sha256=None,
            provider_response_id=None,
            failure_code=failure_code,
        )
        report_index(failed_index, failed_path, status="capture-failed")
        return 1
    finally:
        if provider is not None:
            provider.close()
    index, path = _capture_finished(
        args,
        config=config,
        prior_index=started_index_path,
        attempt_id=attempt_id,
        outcome="SUCCESS",
        completion_sha256=completion.completion_sha256,
        provider_response_id=completion.provider_response_id,
        failure_code=None,
    )
    attempt_inventory._write_private_new(
        args.session_output,
        attempt_inventory.canonical_bytes(session.to_artifact()),
    )
    report_index(index, path)
    return 0


def command_finalize_run(args: argparse.Namespace) -> int:
    suite, config = common_inputs(args)
    result_bytes = attempt_inventory._read_once(args.result)
    result = attempt_inventory._json_object(result_bytes, "target result")
    if errors := target_session.target_result_errors(
        result, suite=suite, config=config, clock=now
    ):
        raise attempt_inventory.AttemptInventoryError(
            "target result failed verification: " + "; ".join(errors)
        )
    result_path = args.result.resolve(strict=True)
    manifest_root = args.manifest_root.resolve(strict=True)
    try:
        relative_path = result_path.relative_to(manifest_root).as_posix()
    except ValueError as exc:
        raise attempt_inventory.AttemptInventoryError(
            "result must remain under the future manifest root"
        ) from exc
    run = result["run"]
    index, path = append_event(
        args,
        config=config,
        event_type="RUN_FINALIZED",
        payload={
            "kind": "RUN_FINALIZED",
            "run_identity": {
                "case_id": run["case_id"],
                "system_id": run["system_id"],
                "variant_id": run["variant_id"],
                "repetition": run["repetition"],
            },
            "result_relative_path": relative_path,
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
        },
        prior_index=args.prior_index,
    )
    report_index(index, path)
    return 0


def _event_counts(index_path: Path) -> tuple[int, int]:
    index = load_json(index_path, "prior attempt index")
    root = index_path.resolve().parent
    capture_count = 0
    finalized_count = 0
    for entry in index["entries"]:
        event_path = attempt_inventory._safe_path(root, entry["event_path"])
        event = load_json(event_path, "attempt event")
        capture_count += event.get("event_type") == "CAPTURE_STARTED"
        finalized_count += event.get("event_type") == "RUN_FINALIZED"
    return capture_count, finalized_count


def command_seal(args: argparse.Namespace) -> int:
    suite, config = common_inputs(args)
    manifest = load_json(args.manifest, "result manifest")
    if errors := campaign.validate_result_manifest(manifest, suite=suite, config=config):
        raise attempt_inventory.AttemptInventoryError(
            "invalid result manifest: " + "; ".join(errors)
        )
    capture_count, finalized_count = _event_counts(args.prior_index)
    if finalized_count != len(config["run_plan"]) or capture_count < finalized_count:
        raise attempt_inventory.AttemptInventoryError(
            "campaign cannot seal before every planned run and capture is present"
        )
    index, path = append_event(
        args,
        config=config,
        event_type="CAMPAIGN_SEALED",
        payload={
            "kind": "CAMPAIGN_SEALED",
            "capture_attempt_count": capture_count,
            "finalized_run_count": finalized_count,
            "result_manifest_sha256": manifest["manifest_sha256"],
            "provider_access_enforced": True,
            "provider_access_control_sha256": args.provider_access_control_sha256,
            "all_artifacts_preserved": True,
            "artifact_inventory_sha256": args.artifact_inventory_sha256,
        },
        prior_index=args.prior_index,
    )
    report_index(index, path)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    suite, config = common_inputs(args)
    result = attempt_inventory.verify_inventory(
        index_path=args.index,
        config=config,
        suite=suite,
        result_manifest_path=args.manifest,
        policy_path=args.policy,
        expected_policy_sha256=args.expected_policy_sha256,
        expected_head_sha256=args.expected_head_sha256,
        expected_event_count=args.expected_event_count,
        clock=now,
    )
    if args.output is not None:
        attempt_inventory._write_private_new(
            args.output, attempt_inventory.canonical_bytes(result)
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("qualification_ready") is True else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)

    def configured(command: argparse.ArgumentParser) -> None:
        command.add_argument("--suite", type=Path, default=ROOT / "evals/cases.json")
        command.add_argument("--config", type=Path, required=True)

    def witnessed(command: argparse.ArgumentParser) -> None:
        configured(command)
        command.add_argument("--campaign-id", required=True)
        command.add_argument("--packet-directory", type=Path, required=True)
        command.add_argument("--witness-adapter", type=Path, required=True)
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--expected-policy-sha256", required=True)

    register = subcommands.add_parser("register")
    witnessed(register)

    capture = subcommands.add_parser("capture")
    witnessed(capture)
    capture.add_argument("--prior-index", type=Path, required=True)
    capture.add_argument("--session", type=Path, required=True)
    capture.add_argument("--adapter", type=Path, required=True)
    capture.add_argument("--env", action="append", default=[])
    capture.add_argument("--timeout", type=int, default=120)
    capture.add_argument("--session-output", type=Path, required=True)

    finalize = subcommands.add_parser("finalize-run")
    witnessed(finalize)
    finalize.add_argument("--prior-index", type=Path, required=True)
    finalize.add_argument("--result", type=Path, required=True)
    finalize.add_argument("--manifest-root", type=Path, required=True)

    seal = subcommands.add_parser("seal")
    witnessed(seal)
    seal.add_argument("--prior-index", type=Path, required=True)
    seal.add_argument("--manifest", type=Path, required=True)
    seal.add_argument("--provider-access-control-sha256", required=True)
    seal.add_argument("--artifact-inventory-sha256", required=True)

    verify = subcommands.add_parser("verify")
    configured(verify)
    verify.add_argument("--index", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--policy", type=Path, required=True)
    verify.add_argument("--expected-policy-sha256", required=True)
    verify.add_argument("--expected-head-sha256", required=True)
    verify.add_argument("--expected-event-count", type=int, required=True)
    verify.add_argument("--output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "register":
            return command_register(args)
        if args.command == "capture":
            return command_capture(args)
        if args.command == "finalize-run":
            return command_finalize_run(args)
        if args.command == "seal":
            return command_seal(args)
        if args.command == "verify":
            return command_verify(args)
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
        attempt_inventory.AttemptInventoryError,
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
