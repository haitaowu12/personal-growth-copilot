#!/usr/bin/env python3
"""Prepare, assemble, and verify privacy-gate-bound persistence authorization."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(
    0,
    str(
        ROOT
        / "plugins/personal-growth-copilot/skills/personal-growth-copilot/scripts"
    ),
)

import persistent_record_store  # noqa: E402
import release_evidence  # noqa: E402

REQUEST_SCHEMA = ROOT / "release/persistence-authorization-request.schema.json"
AUTHORIZATION_SCHEMA = ROOT / "release/persistence-authorization.schema.json"


class PersistenceAuthorizationError(RuntimeError):
    pass


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceAuthorizationError("authorization clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PersistenceAuthorizationError("authorization timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PersistenceAuthorizationError("authorization timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def schema_errors(value: object, path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    store = {
        (ROOT / "release/persistence-authorization.schema.json").resolve().as_uri(): json.loads(
            (ROOT / "release/persistence-authorization.schema.json").read_text(
                encoding="utf-8"
            )
        )
    }
    resolver = RefResolver(base_uri=path.resolve().as_uri(), referrer=schema, store=store)
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema, resolver=resolver, format_checker=FormatChecker()
            ).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def load_object(path: Path, label: str) -> dict[str, Any]:
    return release_evidence.json_object(release_evidence.read_once(path), label)


def source_identity() -> str:
    return release_evidence.source_identity(ROOT)


def relative_path(path: Path, root: Path) -> str:
    if path.is_symlink():
        raise PersistenceAuthorizationError("authorization key path may not be a symlink")
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise PersistenceAuthorizationError(
            "authorization key must remain within the packet root"
        ) from exc


def _verified_privacy_context(
    *,
    index_path: Path,
    policy_path: Path,
    expected_commit: str,
    expected_policy_sha256: str,
    expected_index_sha256: str,
    host_identity_path: Path,
    verifier: Callable[..., dict[str, Any]] = release_evidence.verify,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    verification = verifier(
        index_path=index_path,
        policy_path=policy_path,
        expected_commit=expected_commit,
        expected_policy_sha256=expected_policy_sha256,
        expected_index_sha256=expected_index_sha256,
    )
    if verification.get("verification_status") != "pass":
        raise PersistenceAuthorizationError(
            "release packet verification failed: "
            + "; ".join(verification.get("errors", []))
        )
    index = load_object(index_path, "evidence index")
    policy = load_object(policy_path, "trust policy")
    privacy_ref = index["gates"]["privacy_preflight"]
    if privacy_ref["status"] != "PASS":
        raise PersistenceAuthorizationError("current privacy-preflight gate is not PASS")
    host_identity = load_object(host_identity_path, "privacy host identity")
    if errors := release_evidence.schema_errors(host_identity, "privacy_host"):
        raise PersistenceAuthorizationError(
            "invalid privacy host identity: " + "; ".join(errors)
        )
    host_hash = hashlib.sha256(host_identity_path.read_bytes()).hexdigest()
    if host_hash != policy["privacy_host_identity_sha256"]:
        raise PersistenceAuthorizationError(
            "privacy host identity differs from the owner-frozen policy"
        )
    authority = next(
        (
            item
            for item in policy["authorities"]
            if item["role"] == release_evidence.ROLE_BY_GATE["privacy_preflight"]
        ),
        None,
    )
    if authority is None:
        raise PersistenceAuthorizationError("privacy authority is absent from policy")
    return index, policy, host_identity, authority


def prepare_request(
    *,
    output: Path,
    index_path: Path,
    policy_path: Path,
    host_identity_path: Path,
    storage_root: Path,
    expected_commit: str,
    expected_policy_sha256: str,
    expected_index_sha256: str,
    authorization_id: str,
    issued_at: datetime,
    expires_at: datetime,
    nonce: str,
    verifier: Callable[..., dict[str, Any]] = release_evidence.verify,
) -> dict[str, Any]:
    index, policy, host_identity, authority = _verified_privacy_context(
        index_path=index_path,
        policy_path=policy_path,
        expected_commit=expected_commit,
        expected_policy_sha256=expected_policy_sha256,
        expected_index_sha256=expected_index_sha256,
        host_identity_path=host_identity_path,
        verifier=verifier,
    )
    issued = issued_at.astimezone(timezone.utc)
    expires = expires_at.astimezone(timezone.utc)
    if not issued < expires or expires - issued > timedelta(days=365):
        raise PersistenceAuthorizationError(
            "persistence authorization must be positive and no longer than one year"
        )
    root_identity = persistent_record_store.storage_root_identity(storage_root)
    if root_identity != host_identity["storage_root_sha256"]:
        raise PersistenceAuthorizationError(
            "requested storage root differs from the verified privacy host identity"
        )
    packet_root = index_path.resolve().parent
    key_path = release_evidence.safe_path(packet_root, authority["public_key_path"])
    payload = {
        "domain": "pgc-persistence-authorization-v1",
        "authorization_id": authorization_id,
        "candidate_commit": expected_commit,
        "evidence_index_sha256": index["index_sha256"],
        "privacy_artifact_sha256": index["gates"]["privacy_preflight"][
            "artifact_sha256"
        ],
        "privacy_host_identity_sha256": hashlib.sha256(
            host_identity_path.read_bytes()
        ).hexdigest(),
        "named_host": host_identity["named_host"],
        "environment_id": host_identity["environment_id"],
        "storage_root_sha256": root_identity,
        "issued_at": timestamp(issued),
        "expires_at": timestamp(expires),
        "nonce": nonce,
    }
    request = {
        "schema_version": "1.0",
        "evidence_class": "persistence-authorization-signing-request",
        "payload": payload,
        "key_id": authority["key_id"],
        "public_key_path": relative_path(key_path, output.parent.resolve()),
        "public_key_sha256": authority["public_key_sha256"],
    }
    request["request_sha256"] = release_evidence.digest(request)
    if errors := schema_errors(request, REQUEST_SCHEMA):
        raise PersistenceAuthorizationError(
            "persistence authorization request schema failure: " + "; ".join(errors)
        )
    return request


def assemble(
    *, request_path: Path, signature_path: Path
) -> dict[str, Any]:
    request = load_object(request_path, "persistence authorization request")
    if errors := schema_errors(request, REQUEST_SCHEMA):
        raise PersistenceAuthorizationError("invalid authorization request: " + "; ".join(errors))
    if request["request_sha256"] != release_evidence.object_hash(
        request, "request_sha256"
    ):
        raise PersistenceAuthorizationError("authorization request self-hash mismatch")
    signature = signature_path.read_text(encoding="utf-8").strip()
    try:
        base64.b64decode(signature, validate=True)
    except Exception as exc:
        raise PersistenceAuthorizationError("authorization signature is not base64") from exc
    key = release_evidence.load_bound_public_key(
        request_path.parent.resolve(),
        request["public_key_path"],
        request["public_key_sha256"],
        "privacy authority",
    )
    release_evidence.verify_signature(request["payload"], signature, key)
    authorization = {
        "schema_version": "1.0",
        "evidence_class": "signed-persistence-authorization",
        "payload": request["payload"],
        "key_id": request["key_id"],
        "public_key_path": request["public_key_path"],
        "public_key_sha256": request["public_key_sha256"],
        "signature_base64": signature,
    }
    authorization["authorization_sha256"] = release_evidence.digest(authorization)
    if errors := schema_errors(authorization, AUTHORIZATION_SCHEMA):
        raise PersistenceAuthorizationError(
            "persistence authorization schema failure: " + "; ".join(errors)
        )
    return authorization


def authorization_record(artifact: dict[str, Any]) -> persistent_record_store.HostPersistenceAuthorization:
    payload = artifact["payload"]
    return persistent_record_store.HostPersistenceAuthorization(
        authorization_id=payload["authorization_id"],
        named_host=payload["named_host"],
        environment_id=payload["environment_id"],
        storage_root_sha256=payload["storage_root_sha256"],
        issued_at=payload["issued_at"],
        expires_at=payload["expires_at"],
        candidate_commit=payload["candidate_commit"],
        evidence_index_sha256=payload["evidence_index_sha256"],
        privacy_artifact_sha256=payload["privacy_artifact_sha256"],
        privacy_host_identity_sha256=payload["privacy_host_identity_sha256"],
        key_id=artifact["key_id"],
    )


class SignedPersistenceAuthorizationVerifier:
    """Host verifier for the adapter's authorization boundary."""

    def __init__(
        self,
        *,
        authorization_path: Path,
        expected_candidate_commit: str,
        expected_index_sha256: str,
        expected_privacy_artifact_sha256: str,
    ) -> None:
        self.path = authorization_path.resolve(strict=True)
        self.artifact = load_object(self.path, "signed persistence authorization")
        if errors := schema_errors(self.artifact, AUTHORIZATION_SCHEMA):
            raise PersistenceAuthorizationError(
                "invalid signed persistence authorization: " + "; ".join(errors)
            )
        if self.artifact["authorization_sha256"] != release_evidence.object_hash(
            self.artifact, "authorization_sha256"
        ):
            raise PersistenceAuthorizationError("persistence authorization self-hash mismatch")
        payload = self.artifact["payload"]
        if (
            payload["candidate_commit"] != expected_candidate_commit
            or payload["evidence_index_sha256"] != expected_index_sha256
            or payload["privacy_artifact_sha256"]
            != expected_privacy_artifact_sha256
        ):
            raise PersistenceAuthorizationError(
                "persistence authorization differs from the host's current release anchors"
            )
        key = release_evidence.load_bound_public_key(
            self.path.parent,
            self.artifact["public_key_path"],
            self.artifact["public_key_sha256"],
            "privacy authority",
        )
        release_evidence.verify_signature(
            payload, self.artifact["signature_base64"], key
        )
        self.record = authorization_record(self.artifact)

    def verify(
        self,
        authorization: persistent_record_store.HostPersistenceAuthorization,
        storage_root: Path,
    ) -> bool:
        return (
            authorization == self.record
            and authorization.storage_root_sha256
            == persistent_record_store.storage_root_identity(storage_root)
            and parse_time(authorization.issued_at)
            <= datetime.now(timezone.utc)
            < parse_time(authorization.expires_at)
        )


def write_private_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise PersistenceAuthorizationError("authorization output is create-only")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--index", type=Path, required=True)
    prepare.add_argument("--policy", type=Path, required=True)
    prepare.add_argument("--host-identity", type=Path, required=True)
    prepare.add_argument("--storage-root", type=Path, required=True)
    prepare.add_argument("--expected-policy-sha256", required=True)
    prepare.add_argument("--expected-index-sha256", required=True)
    prepare.add_argument("--authorization-id", required=True)
    prepare.add_argument("--issued-at", required=True)
    prepare.add_argument("--expires-at", required=True)
    prepare.add_argument("--nonce", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    assemble_command = commands.add_parser("assemble")
    assemble_command.add_argument("--request", type=Path, required=True)
    assemble_command.add_argument("--signature", type=Path, required=True)
    assemble_command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            value = prepare_request(
                output=args.output,
                index_path=args.index,
                policy_path=args.policy,
                host_identity_path=args.host_identity,
                storage_root=args.storage_root,
                expected_commit=source_identity(),
                expected_policy_sha256=args.expected_policy_sha256,
                expected_index_sha256=args.expected_index_sha256,
                authorization_id=args.authorization_id,
                issued_at=parse_time(args.issued_at),
                expires_at=parse_time(args.expires_at),
                nonce=args.nonce,
            )
        else:
            value = assemble(
                request_path=args.request, signature_path=args.signature
            )
        write_private_new(args.output, value)
        print(
            json.dumps(
                {"status": "pass", "output": str(args.output)}, indent=2
            )
        )
        return 0
    except (
        OSError,
        subprocess.SubprocessError,
        PersistenceAuthorizationError,
        release_evidence.ReleaseEvidenceError,
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
