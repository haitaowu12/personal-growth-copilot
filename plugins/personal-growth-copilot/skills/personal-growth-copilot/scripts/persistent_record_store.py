#!/usr/bin/env python3
"""Atomic local persistence adapter for the Personal Growth Copilot record contract.

The adapter is disabled unless a trusted host verifier approves one exact,
time-bounded authorization for the exact storage-root filesystem object.  The
authorization is a host boundary, not a model assertion and not a substitute
for the source-witnessed privacy preflight.

Content is stored as canonical JSON in a user-owned mode-0700 directory.  The
host remains responsible for filesystem encryption, backup policy, no-sync
placement, credential isolation, and physical-media deletion guarantees.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Protocol

import record_store


Clock = Callable[[], datetime]
_AUTHORIZATION_ID = re.compile(r"^pauth_[0-9a-f]{32}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_ENVIRONMENT_ID = re.compile(r"^[a-z][a-z0-9-]{7,99}$")
STATE_NAME = "pgc-growth-records.json"
LOCK_NAME = ".pgc-growth-records.lock"
MAX_STATE_BYTES = 50 * 1024 * 1024


class PersistentStoreError(record_store.RecordStoreError):
    """Raised when the persistent host boundary or state file fails closed."""


@dataclass(frozen=True)
class HostPersistenceAuthorization:
    """Content-free host authorization bound to one storage-root object."""

    authorization_id: str
    named_host: str
    environment_id: str
    storage_root_sha256: str
    issued_at: str
    expires_at: str
    candidate_commit: str = "0" * 40
    evidence_index_sha256: str = "0" * 64
    privacy_artifact_sha256: str = "0" * 64
    privacy_host_identity_sha256: str = "0" * 64
    key_id: str = "key-0000000000000000"


class PersistenceAuthorizationVerifier(Protocol):
    """Trusted host boundary; a model-facing caller cannot self-authorize."""

    def verify(
        self, authorization: HostPersistenceAuthorization, storage_root: Path
    ) -> bool: ...


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistentStoreError("store clock must be timezone aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PersistentStoreError("persistent authorization timestamp is invalid") from exc
    return _as_utc(parsed)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def storage_root_identity(path: Path) -> str:
    """Return the same opaque filesystem-object identity used by host discovery."""

    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise PersistentStoreError("storage-root identity is unavailable") from exc
    return hashlib.sha256(
        f"filesystem-object:{metadata.st_dev}:{metadata.st_ino}".encode("utf-8")
    ).hexdigest()


def _bounded_regular_bytes(path: Path, maximum: int = MAX_STATE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PersistentStoreError("persistent state is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise PersistentStoreError("persistent state is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1_048_576, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise PersistentStoreError("persistent state exceeds its size limit")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise PersistentStoreError("persistent state changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json_object(data: bytes) -> dict[str, Any]:
    def unique(pairs):
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PersistentStoreError("persistent state contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PersistentStoreError("persistent state is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PersistentStoreError("persistent state must be a JSON object")
    return value


def _validate_root(path: Path) -> Path:
    if not path.is_absolute():
        raise PersistentStoreError("persistent storage root must be absolute")
    if path.is_symlink():
        raise PersistentStoreError("persistent storage root may not be a symlink")
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise PersistentStoreError("persistent storage root is unavailable") from exc
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise PersistentStoreError("persistent storage root must be a directory")
    if metadata.st_uid != os.geteuid():
        raise PersistentStoreError("persistent storage root must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise PersistentStoreError("persistent storage root must use mode 0700")
    return root


def _validate_authorization(
    authorization: HostPersistenceAuthorization,
    root: Path,
    verifier: PersistenceAuthorizationVerifier,
    now: datetime,
) -> None:
    if not _AUTHORIZATION_ID.fullmatch(authorization.authorization_id):
        raise PersistentStoreError("persistent authorization id is invalid")
    if not authorization.named_host.strip():
        raise PersistentStoreError("persistent authorization requires a named host")
    if not _ENVIRONMENT_ID.fullmatch(authorization.environment_id):
        raise PersistentStoreError("persistent authorization environment id is invalid")
    if not _HASH.fullmatch(authorization.storage_root_sha256):
        raise PersistentStoreError("persistent authorization storage identity is invalid")
    if (
        len(authorization.candidate_commit) != 40
        or any(character not in "0123456789abcdef" for character in authorization.candidate_commit)
        or not _HASH.fullmatch(authorization.evidence_index_sha256)
        or not _HASH.fullmatch(authorization.privacy_artifact_sha256)
        or not _HASH.fullmatch(authorization.privacy_host_identity_sha256)
        or not re.fullmatch(r"^key-[0-9a-f]{16}$", authorization.key_id)
    ):
        raise PersistentStoreError("persistent authorization release binding is invalid")
    if authorization.storage_root_sha256 != storage_root_identity(root):
        raise PersistentStoreError("persistent authorization is bound to another storage root")
    issued = _parse_time(authorization.issued_at)
    expires = _parse_time(authorization.expires_at)
    if not issued <= now < expires:
        raise PersistentStoreError("persistent authorization is not currently valid")
    if expires - issued > timedelta(days=365):
        raise PersistentStoreError("persistent authorization exceeds one year")
    try:
        accepted = verifier.verify(authorization, root)
    except Exception as exc:
        raise PersistentStoreError("host persistence-authorization verifier failed") from exc
    if accepted is not True:
        raise PersistentStoreError("host persistence authorization was not verified")


class PersistentRecordStore:
    """Crash-safe local adapter preserving the in-memory record-store contract."""

    def __init__(
        self,
        *,
        storage_root: Path,
        authorization: HostPersistenceAuthorization,
        authorization_verifier: PersistenceAuthorizationVerifier,
        consent_verifier: record_store.ConsentVerifier,
        clock: Clock | None = None,
        audit_retention_days: int = 90,
    ) -> None:
        if not 1 <= audit_retention_days <= 365:
            raise PersistentStoreError("audit_retention_days must be from 1 through 365")
        self._clock = clock or _system_clock
        now = _as_utc(self._clock())
        self._root = _validate_root(storage_root)
        _validate_authorization(
            authorization, self._root, authorization_verifier, now
        )
        self._authorization = authorization
        self._authorization_verifier = authorization_verifier
        self._consent_verifier = consent_verifier
        self._audit_retention_days = audit_retention_days
        self._state_path = self._root / STATE_NAME
        self._lock_path = self._root / LOCK_NAME
        self._thread_lock = RLock()
        self._inner = record_store.InMemoryRecordStore(
            consent_verifier=consent_verifier,
            clock=self._clock,
        )
        self._store_id = "pstore_" + secrets.token_hex(16)
        self._generation = 0
        self._open_lock_file()
        with self._file_lock():
            self._reload_unlocked()
            if self._generation and self._audit_retention_days != self._state_retention:
                raise PersistentStoreError(
                    "configured audit retention differs from the existing store"
                )

    @property
    def storage_root(self) -> Path:
        return self._root

    @property
    def state_path(self) -> Path:
        return self._state_path

    def _now(self) -> datetime:
        return _as_utc(self._clock())

    def _check_authorized(self) -> None:
        _validate_authorization(
            self._authorization,
            self._root,
            self._authorization_verifier,
            self._now(),
        )

    def _open_lock_file(self) -> None:
        if self._lock_path.is_symlink():
            raise PersistentStoreError("persistent lock file may not be a symlink")
        descriptor = os.open(
            self._lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PersistentStoreError("persistent lock path is not a regular file")
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        with self._thread_lock:
            descriptor = os.open(
                self._lock_path,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    @property
    def _state_retention(self) -> int:
        return getattr(self, "__state_retention", self._audit_retention_days)

    @_state_retention.setter
    def _state_retention(self, value: int) -> None:
        self.__state_retention = value

    def _new_inner(self) -> record_store.InMemoryRecordStore:
        return record_store.InMemoryRecordStore(
            consent_verifier=self._consent_verifier,
            clock=self._clock,
        )

    def _state_payload(self, *, generation: int | None = None) -> dict[str, Any]:
        inner = self._inner
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "evidence_class": "persistent-growth-record-state",
            "store_id": self._store_id,
            "generation": self._generation if generation is None else generation,
            "audit_retention_days": self._audit_retention_days,
            "last_clock_read": (
                _timestamp(inner._last_clock_read)
                if inner._last_clock_read is not None
                else None
            ),
            "current": {
                key: asdict(value) for key, value in sorted(inner._current.items())
            },
            "history": deepcopy(inner._history),
            "previews": {
                key: {
                    "public": asdict(value.public),
                    "proposed_record": deepcopy(value.proposed_record),
                }
                for key, value in sorted(inner._previews.items())
            },
            "tokens": {
                key: {
                    "public": asdict(value.public),
                    "record_id": value.record_id,
                    "revoked": value.revoked,
                    "consumed": value.consumed,
                }
                for key, value in sorted(inner._tokens.items())
            },
            "attestation_records": dict(sorted(inner._attestation_records.items())),
            "audit": [asdict(value) for value in inner._audit],
        }
        payload["state_sha256"] = _digest(payload)
        return payload

    def _validate_state(self, state: dict[str, Any]) -> None:
        expected = {
            "schema_version",
            "evidence_class",
            "store_id",
            "generation",
            "audit_retention_days",
            "last_clock_read",
            "current",
            "history",
            "previews",
            "tokens",
            "attestation_records",
            "audit",
            "state_sha256",
        }
        if set(state) != expected:
            raise PersistentStoreError("persistent state fields do not match the contract")
        if (
            state["schema_version"] != "1.0"
            or state["evidence_class"] != "persistent-growth-record-state"
            or not isinstance(state["store_id"], str)
            or not isinstance(state["generation"], int)
            or isinstance(state["generation"], bool)
            or state["generation"] < 1
            or not isinstance(state["audit_retention_days"], int)
            or isinstance(state["audit_retention_days"], bool)
            or not 1 <= state["audit_retention_days"] <= 365
        ):
            raise PersistentStoreError("persistent state metadata is invalid")
        if state["state_sha256"] != _digest(
            {key: value for key, value in state.items() if key != "state_sha256"}
        ):
            raise PersistentStoreError("persistent state self-hash mismatch")
        for collection in (
            "current",
            "history",
            "previews",
            "tokens",
            "attestation_records",
        ):
            if not isinstance(state[collection], dict):
                raise PersistentStoreError(f"persistent state {collection} is invalid")
        if not isinstance(state["audit"], list):
            raise PersistentStoreError("persistent state audit is invalid")

    def _apply_state(self, state: dict[str, Any]) -> None:
        self._validate_state(state)
        inner = self._new_inner()
        inner._last_clock_read = (
            _parse_time(state["last_clock_read"])
            if state["last_clock_read"] is not None
            else None
        )
        try:
            inner._current = {
                key: record_store.RecordSnapshot(**value)
                for key, value in state["current"].items()
            }
            inner._history = deepcopy(state["history"])
            inner._previews = {
                key: record_store._PreviewState(
                    public=record_store.ChangePreview(
                        **{
                            **value["public"],
                            "delta": tuple(
                                record_store.DeltaEntry(**item)
                                for item in value["public"]["delta"]
                            ),
                        }
                    ),
                    proposed_record=deepcopy(value["proposed_record"]),
                )
                for key, value in state["previews"].items()
            }
            inner._tokens = {
                key: record_store._TokenState(
                    public=record_store.ConsentToken(**value["public"]),
                    record_id=value["record_id"],
                    revoked=value["revoked"],
                    consumed=value["consumed"],
                )
                for key, value in state["tokens"].items()
            }
            inner._attestation_records = dict(state["attestation_records"])
            inner._audit = [
                record_store.AuditEvent(
                    **{
                        **value,
                        "field_paths": tuple(value["field_paths"]),
                    }
                )
                for value in state["audit"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistentStoreError("persistent state contains malformed records") from exc
        self._inner = inner
        self._store_id = state["store_id"]
        self._generation = state["generation"]
        self._state_retention = state["audit_retention_days"]

    def _reload_unlocked(self) -> None:
        if self._state_path.is_symlink():
            raise PersistentStoreError("persistent state may not be a symlink")
        if not self._state_path.exists():
            self._inner = self._new_inner()
            self._store_id = "pstore_" + secrets.token_hex(16)
            self._generation = 0
            self._state_retention = self._audit_retention_days
            return
        metadata = self._state_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise PersistentStoreError("persistent state must be a mode-0600 regular file")
        data = _bounded_regular_bytes(self._state_path)
        state = _json_object(data)
        if data != _canonical_bytes(state):
            raise PersistentStoreError("persistent state must use canonical JSON bytes")
        self._apply_state(state)

    def _atomic_write_unlocked(self, state: dict[str, Any]) -> None:
        data = _canonical_bytes(state)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".pgc-state-", suffix=".json", dir=self._root
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if self._state_path.is_symlink():
                raise PersistentStoreError("persistent state may not be a symlink")
            os.replace(temporary, self._state_path)
            os.chmod(self._state_path, 0o600)
            directory_descriptor = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _purge_audit_unlocked(self, now: datetime) -> int:
        cutoff = now - timedelta(days=self._audit_retention_days)
        before = len(self._inner._audit)
        self._inner._audit = [
            event
            for event in self._inner._audit
            if _parse_time(event.timestamp) >= cutoff
        ]
        return before - len(self._inner._audit)

    def _persist_mutation(self, method: str, *args, **kwargs):
        self._check_authorized()
        with self._file_lock():
            self._reload_unlocked()
            if self._generation and self._state_retention != self._audit_retention_days:
                raise PersistentStoreError(
                    "configured audit retention differs from the existing store"
                )
            previous = self._state_payload() if self._generation else None
            try:
                result = getattr(self._inner, method)(*args, **kwargs)
                self._purge_audit_unlocked(self._now())
                next_generation = self._generation + 1
                state = self._state_payload(generation=next_generation)
                self._atomic_write_unlocked(state)
                self._generation = next_generation
                self._state_retention = self._audit_retention_days
                return deepcopy(result)
            except Exception:
                if previous is not None:
                    self._apply_state(previous)
                else:
                    self._inner = self._new_inner()
                    self._generation = 0
                raise

    def _read(self, method: str, *args, **kwargs):
        self._check_authorized()
        with self._file_lock():
            self._reload_unlocked()
            target = getattr(self._inner, method)
            value = target(*args, **kwargs) if callable(target) else target
            return deepcopy(value)

    def preview_upsert(self, proposed_record: dict[str, Any], purpose: str, **kwargs):
        return self._persist_mutation(
            "preview_upsert", proposed_record, purpose, **kwargs
        )

    def preview_correction(self, record_id: str, **kwargs):
        return self._persist_mutation("preview_correction", record_id, **kwargs)

    def preview_delete(self, record_id: str, purpose: str, **kwargs):
        return self._persist_mutation(
            "preview_delete", record_id, purpose, **kwargs
        )

    def issue_consent(
        self,
        preview_id: str,
        confirmation: record_store.HostUserConfirmation,
        **kwargs,
    ):
        return self._persist_mutation(
            "issue_consent", preview_id, confirmation, **kwargs
        )

    def revoke_consent(self, token_id: str):
        return self._persist_mutation("revoke_consent", token_id)

    def commit(self, preview_id: str, token_id: str):
        return self._persist_mutation("commit", preview_id, token_id)

    def delete(self, preview_id: str, token_id: str):
        return self._persist_mutation("delete", preview_id, token_id)

    def read(self, record_id: str, revision_id: str | None = None):
        return self._read("read", record_id, revision_id)

    def get_preview(self, preview_id: str):
        # get_preview may purge expired preview/token state and therefore persists.
        return self._persist_mutation("get_preview", preview_id)

    def export(self, record_id: str):
        return self._read("export", record_id)

    def content_inventory(self, record_id: str):
        return self._read("content_inventory", record_id)

    def retention_inventory(self, record_id: str):
        return self._read("retention_inventory", record_id)

    @property
    def audit_events(self):
        return self._read("audit_events")

    def enforce_retention(self) -> int:
        """Purge audit metadata older than the configured bounded retention."""

        self._check_authorized()
        with self._file_lock():
            self._reload_unlocked()
            previous = self._state_payload() if self._generation else None
            try:
                removed = self._purge_audit_unlocked(self._now())
                if removed:
                    next_generation = self._generation + 1
                    self._atomic_write_unlocked(
                        self._state_payload(generation=next_generation)
                    )
                    self._generation = next_generation
                return removed
            except Exception:
                if previous is not None:
                    self._apply_state(previous)
                raise
