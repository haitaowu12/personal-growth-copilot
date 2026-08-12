"""Externally witnessed, append-only target-execution attempt inventory."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import stat
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from jsonschema import Draft202012Validator, FormatChecker

import campaign
import target_session

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_EVENT_SCHEMA = ROOT / "evals/attempt-event.schema.json"
ATTEMPT_RECEIPT_SCHEMA = ROOT / "evals/attempt-witness-receipt.schema.json"
ATTEMPT_INDEX_SCHEMA = ROOT / "evals/attempt-inventory-index.schema.json"
TRUST_POLICY_SCHEMA = ROOT / "release/trust-policy.schema.json"
MAXIMUM_FILE_BYTES = 10_485_760


class AttemptInventoryError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def object_hash(value: dict[str, Any], field: str) -> str:
    return digest({key: child for key, child in value.items() if key != field})


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AttemptInventoryError("attempt timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttemptInventoryError("attempt timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def _schema_errors(value: object, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: "
        f"violates {error.validator}"
        for error in sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def _read_once(path: Path, maximum: int = MAXIMUM_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AttemptInventoryError("attempt evidence file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise AttemptInventoryError("attempt evidence must be a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1_048_576, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise AttemptInventoryError("attempt evidence exceeds its size limit")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AttemptInventoryError("attempt evidence changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AttemptInventoryError(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise AttemptInventoryError(f"{label} contains a non-finite number")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise AttemptInventoryError(f"{label} contains a non-finite number")
        return parsed

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AttemptInventoryError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AttemptInventoryError(f"{label} must be an object")
    return value


def _safe_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise AttemptInventoryError("attempt evidence path must remain in its packet")
    candidate = root / relative
    current = candidate
    while current != root:
        if current.is_symlink():
            raise AttemptInventoryError("attempt evidence path may not traverse a symlink")
        current = current.parent
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise AttemptInventoryError("attempt evidence path is unavailable") from exc
    if root not in resolved.parents:
        raise AttemptInventoryError("attempt evidence path escaped its packet")
    return resolved


def _write_private_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


def _canonical_public_key(public_key: bytes) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(prefix="pgc-attempt-key-") as directory_name:
        key_path = Path(directory_name) / "public.pem"
        key_path.write_bytes(public_key)
        description = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(key_path), "-text", "-noout"],
            capture_output=True,
            check=False,
            timeout=30,
        )
        canonical = subprocess.run(
            ["openssl", "pkey", "-pubin", "-in", str(key_path), "-pubout", "-outform", "DER"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    if (
        description.returncode != 0
        or canonical.returncode != 0
        or b"ED25519" not in (description.stdout + description.stderr).upper()
    ):
        raise AttemptInventoryError("attempt witness key is not Ed25519")
    return public_key, hashlib.sha256(canonical.stdout).hexdigest()


def _verify_signature(payload: dict[str, Any], signature: str, public_key: bytes) -> None:
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttemptInventoryError("attempt witness signature is invalid base64") from exc
    with tempfile.TemporaryDirectory(prefix="pgc-attempt-signature-") as directory_name:
        directory = Path(directory_name)
        key_path = directory / "public.pem"
        payload_path = directory / "payload.json"
        signature_path = directory / "signature.bin"
        key_path.write_bytes(public_key)
        payload_path.write_bytes(canonical_bytes(payload))
        signature_path.write_bytes(signature_bytes)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(key_path),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    if result.returncode != 0:
        raise AttemptInventoryError("attempt witness signature verification failed")


def load_attempt_authority(
    *,
    policy_path: Path,
    expected_policy_sha256: str,
    candidate_commit: str,
) -> tuple[dict[str, Any], bytes, datetime, str, str]:
    policy_root = policy_path.resolve().parent
    policy = _json_object(_read_once(policy_path), "attempt trust policy")
    if errors := _schema_errors(policy, TRUST_POLICY_SCHEMA):
        raise AttemptInventoryError("invalid attempt trust policy: " + "; ".join(errors))
    if object_hash(policy, "policy_sha256") != policy["policy_sha256"]:
        raise AttemptInventoryError("attempt trust policy self-hash mismatch")
    if policy["policy_sha256"] != expected_policy_sha256:
        raise AttemptInventoryError("attempt trust policy differs from its external anchor")
    if policy["status"] != "CONFIGURED" or policy["candidate_commit"] != candidate_commit:
        raise AttemptInventoryError("attempt trust policy is not configured for the candidate")
    frozen_at = _parse_time(policy["frozen_at"])
    campaign_id = policy["attempt_campaign_id"]
    selected = [
        authority
        for authority in policy["authorities"]
        if authority["role"] == "attempt_log_authority"
    ]
    if len(selected) != 1 or selected[0]["allowed_gates"] != ["attempt_inventory"]:
        raise AttemptInventoryError("attempt trust policy requires one attempt-log authority")
    authority = selected[0]
    key_path = _safe_path(policy_root, authority["public_key_path"])
    key_bytes = _read_once(key_path, maximum=65_536)
    if hashlib.sha256(key_bytes).hexdigest() != authority["public_key_sha256"]:
        raise AttemptInventoryError("attempt witness public-key hash mismatch")
    key_bytes, _ = _canonical_public_key(key_bytes)
    return authority, key_bytes, frozen_at, campaign_id, policy["target_config_sha256"]


def build_event(
    *,
    campaign_id: str,
    config: dict[str, Any],
    sequence: int,
    previous_event_sha256: str | None,
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> dict[str, Any]:
    event = {
        "schema_version": "1.0",
        "domain": "pgc-attempt-ledger-event-v1",
        "campaign_id": campaign_id,
        "candidate_commit": config["source_commit"],
        "config_sha256": target_session._digest(config),
        "run_plan_sha256": target_session._digest(config["run_plan"]),
        "sequence": sequence,
        "previous_event_sha256": previous_event_sha256,
        "event_type": event_type,
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": deepcopy(payload),
    }
    event["event_sha256"] = digest(event)
    errors = _schema_errors(event, ATTEMPT_EVENT_SCHEMA)
    if errors or payload.get("kind") != event_type:
        raise AttemptInventoryError(
            "attempt event is invalid: " + "; ".join(errors or ["payload kind mismatch"])
        )
    return event


def _verify_receipt(
    *,
    event: dict[str, Any],
    receipt: dict[str, Any],
    authority: dict[str, Any],
    public_key: bytes,
) -> datetime:
    if errors := _schema_errors(receipt, ATTEMPT_RECEIPT_SCHEMA):
        raise AttemptInventoryError("invalid witness receipt: " + "; ".join(errors))
    payload = receipt["payload"]
    expected = {
        "campaign_id": event["campaign_id"],
        "candidate_commit": event["candidate_commit"],
        "event_sha256": event["event_sha256"],
        "sequence": event["sequence"],
        "previous_event_sha256": event["previous_event_sha256"],
    }
    if receipt["key_id"] != authority["key_id"] or any(
        payload[field] != value for field, value in expected.items()
    ):
        raise AttemptInventoryError("witness receipt is bound to another event or authority")
    event_time = _parse_time(event["occurred_at"])
    witnessed_at = _parse_time(payload["witnessed_at"])
    if witnessed_at < event_time:
        raise AttemptInventoryError("witness receipt predates its event")
    _verify_signature(payload, receipt["signature_base64"], public_key)
    return witnessed_at


def append_witnessed_event(
    *,
    config: dict[str, Any],
    campaign_id: str,
    prior_index_path: Path | None,
    event_type: str,
    payload: dict[str, Any],
    witness_adapter: Path,
    policy_path: Path,
    expected_policy_sha256: str,
    event_output: Path,
    receipt_output: Path,
    index_output: Path,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    (
        authority,
        public_key,
        policy_frozen_at,
        policy_campaign_id,
        policy_config_sha256,
    ) = load_attempt_authority(
        policy_path=policy_path,
        expected_policy_sha256=expected_policy_sha256,
        candidate_commit=config["source_commit"],
    )
    if campaign_id != policy_campaign_id:
        raise AttemptInventoryError(
            "campaign id differs from the owner-anchored attempt epoch"
        )
    if target_session._digest(config) != policy_config_sha256:
        raise AttemptInventoryError(
            "target config differs from the owner-frozen release policy"
        )
    if witness_adapter.is_symlink() or not witness_adapter.is_file() or not os.access(
        witness_adapter, os.X_OK
    ):
        raise AttemptInventoryError("witness adapter must be an executable non-symlink file")
    if any(
        path.exists() or path.is_symlink()
        for path in (event_output, receipt_output, index_output)
    ):
        raise AttemptInventoryError("attempt outputs are create-only and already exist")
    if prior_index_path is None:
        entries: list[dict[str, Any]] = []
    else:
        if prior_index_path.resolve().parent != index_output.resolve().parent:
            raise AttemptInventoryError("attempt index versions must share one packet directory")
        prior = _json_object(_read_once(prior_index_path), "prior attempt index")
        if errors := _schema_errors(prior, ATTEMPT_INDEX_SCHEMA):
            raise AttemptInventoryError("invalid prior attempt index: " + "; ".join(errors))
        if object_hash(prior, "index_sha256") != prior["index_sha256"]:
            raise AttemptInventoryError("prior attempt index self-hash mismatch")
        if (
            prior["campaign_id"] != campaign_id
            or prior["candidate_commit"] != config["source_commit"]
            or prior["config_sha256"] != target_session._digest(config)
            or prior["run_plan_sha256"] != target_session._digest(config["run_plan"])
        ):
            raise AttemptInventoryError("prior attempt index belongs to another campaign")
        entries = deepcopy(prior["entries"])
    sequence = len(entries)
    previous_hash = entries[-1]["event_sha256"] if entries else None
    occurred_at = clock()
    if not isinstance(occurred_at, datetime):
        raise AttemptInventoryError("attempt event clock must return a datetime")
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise AttemptInventoryError("attempt event clock must be timezone aware")
    if occurred_at.astimezone(timezone.utc) < policy_frozen_at:
        raise AttemptInventoryError("attempt event predates the owner-anchored policy freeze")
    event = build_event(
        campaign_id=campaign_id,
        config=config,
        sequence=sequence,
        previous_event_sha256=previous_hash,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at,
    )
    result = subprocess.run(
        [str(witness_adapter.resolve())],
        input=canonical_bytes(event),
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0 or result.stderr:
        raise AttemptInventoryError("external witness adapter rejected the event")
    receipt = _json_object(result.stdout, "witness adapter response")
    _verify_receipt(
        event=event,
        receipt=receipt,
        authority=authority,
        public_key=public_key,
    )
    root = index_output.resolve().parent
    for output in (event_output, receipt_output):
        try:
            output.resolve().relative_to(root)
        except ValueError as exc:
            raise AttemptInventoryError("attempt outputs must remain in the packet directory") from exc
    event_bytes = canonical_bytes(event)
    receipt_bytes = canonical_bytes(receipt)
    entries.append(
        {
            "sequence": sequence,
            "event_path": event_output.resolve().relative_to(root).as_posix(),
            "event_sha256": event["event_sha256"],
            "receipt_path": receipt_output.resolve().relative_to(root).as_posix(),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        }
    )
    index = {
        "schema_version": "1.0",
        "campaign_id": campaign_id,
        "candidate_commit": config["source_commit"],
        "config_sha256": target_session._digest(config),
        "run_plan_sha256": target_session._digest(config["run_plan"]),
        "entries": entries,
    }
    index["index_sha256"] = digest(index)
    if errors := _schema_errors(index, ATTEMPT_INDEX_SCHEMA):
        raise AttemptInventoryError("new attempt index is invalid: " + "; ".join(errors))
    _write_private_new(event_output, event_bytes)
    _write_private_new(receipt_output, receipt_bytes)
    _write_private_new(index_output, canonical_bytes(index))
    return index


def _identity_key(identity: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        identity["case_id"],
        identity["system_id"],
        identity["variant_id"],
        identity["repetition"],
    )


def verify_inventory(
    *,
    index_path: Path,
    config: dict[str, Any],
    suite: dict[str, Any],
    result_manifest_path: Path,
    policy_path: Path,
    expected_policy_sha256: str,
    expected_head_sha256: str,
    expected_event_count: int,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    errors: list[str] = []
    hard_failures: set[str] = set()
    try:
        (
            authority,
            public_key,
            policy_frozen_at,
            policy_campaign_id,
            policy_config_sha256,
        ) = load_attempt_authority(
            policy_path=policy_path,
            expected_policy_sha256=expected_policy_sha256,
            candidate_commit=config["source_commit"],
        )
        index = _json_object(_read_once(index_path), "attempt inventory index")
        result_manifest = _json_object(
            _read_once(result_manifest_path), "attempt result manifest"
        )
    except (
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
        AttemptInventoryError,
    ) as exc:
        return {
            "verification_status": "fail",
            "inventory_status": "FAIL",
            "qualification_ready": False,
            "errors": [str(exc)],
            "hard_failures": [],
        }
    errors.extend(_schema_errors(index, ATTEMPT_INDEX_SCHEMA))
    try:
        errors.extend(
            target_session.validate_target_config(deepcopy(config), deepcopy(suite))
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"malformed target config: {type(exc).__name__}")
    try:
        campaign._require_full_suite_scope(suite, config)
    except (KeyError, TypeError, campaign.CampaignError) as exc:
        errors.append(str(exc))
    try:
        verification_time = clock()
        if (
            not isinstance(verification_time, datetime)
            or verification_time.tzinfo is None
            or verification_time.utcoffset() is None
        ):
            raise AttemptInventoryError(
                "attempt verification clock must be timezone aware"
            )
        verification_time = verification_time.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, AttemptInventoryError) as exc:
        errors.append(str(exc))
    if errors:
        return {
            "verification_status": "fail",
            "inventory_status": "FAIL",
            "qualification_ready": False,
            "errors": errors,
            "hard_failures": [],
        }
    if object_hash(index, "index_sha256") != index["index_sha256"]:
        errors.append("attempt inventory index self-hash mismatch")
    if index["campaign_id"] != policy_campaign_id:
        errors.append("attempt inventory differs from the owner-anchored attempt epoch")
    if target_session._digest(config) != policy_config_sha256:
        errors.append("target config differs from the owner-frozen release policy")
    if (
        index["candidate_commit"] != config["source_commit"]
        or index["config_sha256"] != target_session._digest(config)
        or index["run_plan_sha256"] != target_session._digest(config["run_plan"])
    ):
        errors.append("attempt inventory index differs from the frozen target config")
    entries = index["entries"]
    if len(entries) != expected_event_count or entries[-1]["event_sha256"] != expected_head_sha256:
        errors.append("attempt inventory differs from the external witness head/count")
    if [entry["sequence"] for entry in entries] != list(range(len(entries))):
        errors.append("attempt inventory sequences are not contiguous")
    if len({entry["event_path"] for entry in entries}) != len(entries) or len(
        {entry["receipt_path"] for entry in entries}
    ) != len(entries):
        errors.append("attempt inventory event and receipt paths must be unique")
    try:
        manifest_errors = campaign.validate_result_manifest(
            result_manifest, suite=suite, config=config
        )
    except (KeyError, TypeError, AttemptInventoryError) as exc:
        manifest_errors = [f"malformed result manifest: {type(exc).__name__}"]
    if manifest_errors:
        errors.append("invalid result manifest: " + "; ".join(manifest_errors))
    result_artifacts: list[dict[str, Any]] = []
    if not manifest_errors:
        try:
            result_artifacts = campaign.load_manifest_results(
                manifest=result_manifest,
                manifest_path=result_manifest_path,
                suite=suite,
                config=config,
                clock=lambda: verification_time,
            )
        except (KeyError, TypeError, campaign.CampaignError) as exc:
            errors.append(f"invalid manifested result set: {exc}")
    expected_plan = {_identity_key(identity) for identity in config["run_plan"]}
    manifest_by_identity: dict[
        tuple[str, str, str, int], tuple[dict[str, Any], dict[str, Any]]
    ] = {}
    if not manifest_errors and len(result_artifacts) == len(result_manifest["results"]):
        manifest_by_identity = {
            _identity_key(entry["run_identity"]): (entry, artifact)
            for entry, artifact in zip(
                result_manifest["results"], result_artifacts, strict=True
            )
        }
    root = index_path.resolve().parent
    previous_hash: str | None = None
    previous_witnessed: datetime | None = None
    nonces: set[str] = set()
    starts: dict[str, dict[str, Any]] = {}
    start_times: dict[str, datetime] = {}
    finished: set[str] = set()
    finishes: dict[str, dict[str, Any]] = {}
    finish_times: dict[str, datetime] = {}
    successful: set[str] = set()
    capture_keys: set[tuple[Any, ...]] = set()
    response_ids: set[str] = set()
    finalized: set[tuple[str, str, str, int]] = set()
    capture_runs: set[tuple[str, str, str, int]] = set()
    registered = 0
    sealed = 0
    seal_payload: dict[str, Any] | None = None
    for position, entry in enumerate(entries):
        try:
            event_path = _safe_path(root, entry["event_path"])
            receipt_path = _safe_path(root, entry["receipt_path"])
            event_bytes = _read_once(event_path)
            receipt_bytes = _read_once(receipt_path)
            event = _json_object(event_bytes, "attempt event")
            receipt = _json_object(receipt_bytes, "attempt receipt")
            event_errors = _schema_errors(event, ATTEMPT_EVENT_SCHEMA)
            if event_errors:
                raise AttemptInventoryError("invalid attempt event: " + "; ".join(event_errors))
            if event["event_type"] != event["payload"].get("kind"):
                raise AttemptInventoryError("attempt event type and payload kind differ")
            if event["event_sha256"] != object_hash(event, "event_sha256"):
                raise AttemptInventoryError("attempt event self-hash mismatch")
            if event["event_sha256"] != entry["event_sha256"]:
                raise AttemptInventoryError("attempt index event hash mismatch")
            if hashlib.sha256(receipt_bytes).hexdigest() != entry["receipt_sha256"]:
                raise AttemptInventoryError("attempt receipt file hash mismatch")
            if (
                event["campaign_id"] != index["campaign_id"]
                or event["candidate_commit"] != config["source_commit"]
                or event["config_sha256"] != target_session._digest(config)
                or event["run_plan_sha256"] != target_session._digest(config["run_plan"])
                or event["sequence"] != position
                or event["previous_event_sha256"] != previous_hash
            ):
                raise AttemptInventoryError("attempt event chain or campaign binding mismatch")
            event_time = _parse_time(event["occurred_at"])
            if event_time < policy_frozen_at:
                raise AttemptInventoryError(
                    "attempt event predates the owner-anchored policy freeze"
                )
            if event_time > verification_time + timedelta(minutes=5):
                raise AttemptInventoryError(
                    "attempt event is implausibly in the future"
                )
            if previous_witnessed is not None and event_time < previous_witnessed:
                raise AttemptInventoryError("attempt event predates the prior witness receipt")
            witnessed = _verify_receipt(
                event=event,
                receipt=receipt,
                authority=authority,
                public_key=public_key,
            )
            if witnessed > verification_time + timedelta(minutes=5):
                raise AttemptInventoryError(
                    "attempt witness receipt is implausibly in the future"
                )
            if witnessed < policy_frozen_at:
                raise AttemptInventoryError(
                    "attempt witness receipt predates the owner-anchored policy freeze"
                )
            nonce = receipt["payload"]["nonce"]
            if nonce in nonces:
                raise AttemptInventoryError("attempt witness nonce was reused")
            nonces.add(nonce)
            previous_hash = event["event_sha256"]
            previous_witnessed = witnessed
            payload = event["payload"]
            event_type = event["event_type"]
            if event_type == "CAMPAIGN_REGISTERED":
                registered += 1
                if position != 0 or payload["planned_run_count"] != len(config["run_plan"]):
                    raise AttemptInventoryError("campaign registration does not bind the run plan")
            elif event_type == "CAPTURE_STARTED":
                identity_key = _identity_key(payload["run_identity"])
                capture_key = (
                    *identity_key,
                    payload["turn_id"],
                )
                if identity_key not in expected_plan or identity_key in finalized:
                    raise AttemptInventoryError("capture start is outside or after its planned run")
                if payload["attempt_id"] in starts or capture_key in capture_keys:
                    raise AttemptInventoryError("capture retry or attempt id reuse is prohibited")
                starts[payload["attempt_id"]] = payload
                start_times[payload["attempt_id"]] = event_time
                capture_keys.add(capture_key)
                capture_runs.add(identity_key)
            elif event_type == "CAPTURE_FINISHED":
                attempt_id = payload["attempt_id"]
                if attempt_id not in starts or attempt_id in finished:
                    raise AttemptInventoryError("capture finish lacks one open attempt")
                finished.add(attempt_id)
                finishes[attempt_id] = payload
                finish_times[attempt_id] = event_time
                if payload["outcome"] == "SUCCESS":
                    if (
                        payload["completion_sha256"] is None
                        or payload["provider_response_id"] is None
                        or payload["failure_code"] is not None
                    ):
                        raise AttemptInventoryError("successful capture completion is incomplete")
                    if payload["provider_response_id"] in response_ids:
                        raise AttemptInventoryError("provider response id was reused in the inventory")
                    response_ids.add(payload["provider_response_id"])
                    successful.add(attempt_id)
                else:
                    if (
                        payload["completion_sha256"] is not None
                        or payload["provider_response_id"] is not None
                        or payload["failure_code"] is None
                    ):
                        raise AttemptInventoryError("failed capture completion is malformed")
                    hard_failures.add(f"CAPTURE_{payload['outcome']}")
            elif event_type == "RUN_FINALIZED":
                identity_key = _identity_key(payload["run_identity"])
                manifested = manifest_by_identity.get(identity_key)
                if identity_key not in expected_plan or identity_key in finalized:
                    raise AttemptInventoryError("run finalization is duplicate or unplanned")
                if identity_key not in capture_runs:
                    raise AttemptInventoryError("run finalized without a witnessed capture")
                run_attempts = {
                    attempt_id
                    for attempt_id, start in starts.items()
                    if _identity_key(start["run_identity"]) == identity_key
                }
                if not run_attempts or not run_attempts.issubset(successful):
                    raise AttemptInventoryError(
                        "run finalized before every witnessed capture succeeded"
                    )
                if manifested is None:
                    raise AttemptInventoryError(
                        "run finalization lacks one verified manifested result"
                    )
                manifest_entry, result_artifact = manifested
                if (
                    manifest_entry["relative_path"] != payload["result_relative_path"]
                    or manifest_entry["sha256"] != payload["result_sha256"]
                ):
                    raise AttemptInventoryError("run finalization differs from the result manifest")
                ordered_attempts = [
                    attempt_id
                    for attempt_id, start in starts.items()
                    if _identity_key(start["run_identity"]) == identity_key
                ]
                result_captures = result_artifact["captures"]
                if len(ordered_attempts) != len(result_captures):
                    raise AttemptInventoryError(
                        "witnessed captures do not exactly cover the result captures"
                    )
                for attempt_id, result_capture in zip(
                    ordered_attempts, result_captures, strict=True
                ):
                    start = starts[attempt_id]
                    finish = finishes[attempt_id]
                    captured_at = _parse_time(result_capture["captured_at"])
                    if (
                        start["turn_id"] != result_capture["turn_id"]
                        or start["request_sha256"] != result_capture["request_sha256"]
                        or finish["completion_sha256"]
                        != result_capture["completion_sha256"]
                        or finish["provider_response_id"]
                        != result_capture["provider_response_id"]
                        or not start_times[attempt_id]
                        <= captured_at
                        <= finish_times[attempt_id]
                    ):
                        raise AttemptInventoryError(
                            "witnessed capture differs from the finalized result"
                        )
                finalized.add(identity_key)
            elif event_type == "CAMPAIGN_SEALED":
                sealed += 1
                if position != len(entries) - 1:
                    raise AttemptInventoryError("campaign seal must be the final witnessed event")
                seal_payload = payload
        except (OSError, subprocess.SubprocessError, KeyError, TypeError, AttemptInventoryError) as exc:
            errors.append(f"event {position}: {exc}")
    if registered != 1:
        errors.append("attempt inventory requires exactly one campaign registration")
    if sealed != 1 or seal_payload is None:
        errors.append("attempt inventory requires exactly one final campaign seal")
    if set(starts) != finished:
        errors.append("every witnessed capture start must have one finish")
    if finalized != expected_plan:
        errors.append("finalized runs do not exactly cover the frozen run plan")
    if seal_payload is not None:
        if (
            seal_payload["capture_attempt_count"] != len(starts)
            or seal_payload["finalized_run_count"] != len(finalized)
            or seal_payload["result_manifest_sha256"]
            != result_manifest.get("manifest_sha256")
        ):
            errors.append("campaign seal counts or manifest binding mismatch")
    qualification_ready = not errors and not hard_failures
    assertions = {
        "immutable_inventory": not errors,
        "all_attempts_accounted_for": not errors and set(starts) == finished,
        "submitted_results_complete": not errors and finalized == expected_plan,
        "provider_access_enforced": bool(
            seal_payload and seal_payload.get("provider_access_enforced") is True
        ),
        "preregistered_run_plan_bound": registered == 1 and not errors,
        "external_witness_receipts_verified": not errors,
        "all_artifacts_preserved": bool(
            seal_payload and seal_payload.get("all_artifacts_preserved") is True
        ),
        "omitted_attempt_count": 0 if not errors else -1,
        "attempt_count": len(starts),
        "submitted_result_count": len(finalized),
    }
    result = {
        "schema_version": "1.0",
        "evidence_class": "externally-witnessed-attempt-inventory",
        "qualification_claim_allowed": False,
        "verification_status": "pass" if not errors else "fail",
        "inventory_status": "PASS" if qualification_ready else "FAIL",
        "qualification_ready": qualification_ready,
        "candidate_commit": config["source_commit"],
        "campaign_id": index["campaign_id"],
        "config_sha256": target_session._digest(config),
        "run_plan_sha256": target_session._digest(config["run_plan"]),
        "result_manifest_sha256": result_manifest.get("manifest_sha256"),
        "witness_head_sha256": entries[-1]["event_sha256"],
        "event_count": len(entries),
        "assertions": assertions,
        "provider_access_control_sha256": (
            seal_payload.get("provider_access_control_sha256")
            if seal_payload is not None
            else None
        ),
        "artifact_inventory_sha256": (
            seal_payload.get("artifact_inventory_sha256")
            if seal_payload is not None
            else None
        ),
        "hard_failures": sorted(hard_failures),
        "errors": errors,
    }
    result["inventory_sha256"] = digest(result)
    return result


def event_entries(index: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return deepcopy(index["entries"])
