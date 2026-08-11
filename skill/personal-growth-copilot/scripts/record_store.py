#!/usr/bin/env python3
"""Host-neutral conformance target for consented growth-record operations.

The implementation is deliberately in-memory and non-persistent. It requires a
host-supplied user-confirmation verifier and owns its clock. Persistent adapters
must preserve this contract inside a real transaction and separately pass the
host privacy preflight.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable, Literal, Protocol

from growth_record import COLLECTIONS, validate_record

Operation = Literal["CREATE", "UPDATE", "DELETE"]
Clock = Callable[[], datetime]
_MISSING = object()
_OPAQUE_ATTESTATION_ID = re.compile(r"^att_[0-9a-f]{32}$")


class RecordStoreError(RuntimeError):
    """Base error for controlled record operations."""


class RecordNotFound(RecordStoreError):
    pass


class InvalidRecord(RecordStoreError):
    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("invalid growth record: " + "; ".join(errors))


class ConsentError(RecordStoreError):
    pass


class RevisionConflict(RecordStoreError):
    pass


@dataclass(frozen=True)
class DeltaEntry:
    operation: Literal["ADD", "REPLACE", "REMOVE"]
    path: str
    before: Any
    after: Any


@dataclass(frozen=True)
class ChangePreview:
    preview_id: str
    operation: Operation
    record_id: str
    base_revision_id: str | None
    proposed_revision_id: str | None
    purpose: str
    created_at: str
    expires_at: str
    delta: tuple[DeltaEntry, ...]


@dataclass(frozen=True)
class HostUserConfirmation:
    """Opaque host attestation; never put user content in ``attestation_id``."""

    attestation_id: str
    preview_id: str
    confirmed_at: str


class ConsentVerifier(Protocol):
    """Trusted host boundary that a model-facing caller cannot self-assert."""

    def verify(
        self, confirmation: HostUserConfirmation, preview: ChangePreview
    ) -> bool: ...


@dataclass(frozen=True)
class ConsentToken:
    token_id: str
    preview_id: str
    attestation_id: str
    issued_at: str
    expires_at: str


@dataclass(frozen=True)
class RecordSnapshot:
    record_id: str
    revision_id: str
    record: dict[str, Any]


@dataclass(frozen=True)
class CommitResult:
    status: Literal["committed"]
    operation: Literal["CREATE", "UPDATE"]
    record_id: str
    revision_id: str
    audit_event_id: str


@dataclass(frozen=True)
class DeletionResult:
    status: Literal["deleted"]
    record_id: str
    content_revisions_deleted: int
    pending_previews_deleted: int
    record_present_after: bool
    content_present_after: bool
    audit_metadata_retained: bool
    retained_audit_events: int
    audit_event_id: str


@dataclass(frozen=True)
class RevocationResult:
    status: Literal["revoked", "already-revoked", "already-consumed"]
    token_id: str


@dataclass(frozen=True)
class ExportResult:
    record_id: str
    revision_id: str
    content_sha256: str
    record: dict[str, Any]


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    record_id: str
    revision_before: str | None
    revision_after: str | None
    operation: Operation
    field_paths: tuple[str, ...]
    consent_token_id: str
    timestamp: str
    result: Literal["committed", "deleted"]


class RecordStore(Protocol):
    """Minimal interface a host adapter must preserve."""

    def preview_upsert(
        self, proposed_record: dict[str, Any], purpose: str
    ) -> ChangePreview: ...

    def issue_consent(
        self, preview_id: str, confirmation: HostUserConfirmation
    ) -> ConsentToken: ...

    def commit(self, preview_id: str, token_id: str) -> CommitResult: ...

    def export(self, record_id: str) -> ExportResult: ...

    def delete(self, preview_id: str, token_id: str) -> DeletionResult: ...


@dataclass
class _PreviewState:
    public: ChangePreview
    proposed_record: dict[str, Any] | None


@dataclass
class _TokenState:
    public: ConsentToken
    record_id: str
    revoked: bool = False
    consumed: bool = False


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _revision_id() -> str:
    return "rev-" + secrets.token_hex(24)


def _path(parent: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}" if parent else f"/{escaped}"


def _diff(before: Any, after: Any, parent: str = "") -> list[DeltaEntry]:
    if before is _MISSING:
        return [DeltaEntry("ADD", parent or "/", None, deepcopy(after))]
    if after is _MISSING:
        return [DeltaEntry("REMOVE", parent or "/", deepcopy(before), None)]
    if isinstance(before, dict) and isinstance(after, dict):
        result: list[DeltaEntry] = []
        for key in sorted(before.keys() | after.keys()):
            result.extend(
                _diff(
                    before.get(key, _MISSING),
                    after.get(key, _MISSING),
                    _path(parent, key),
                )
            )
        return result
    if before != after:
        return [DeltaEntry("REPLACE", parent or "/", deepcopy(before), deepcopy(after))]
    return []


class InMemoryRecordStore:
    """Thread-safe, non-persistent reference implementation for conformance."""

    def __init__(
        self,
        *,
        consent_verifier: ConsentVerifier,
        clock: Clock | None = None,
    ) -> None:
        self._consent_verifier = consent_verifier
        self._clock = clock or _system_clock
        self._last_clock_read: datetime | None = None
        self._lock = RLock()
        self._current: dict[str, RecordSnapshot] = {}
        self._history: dict[str, dict[str, dict[str, Any]]] = {}
        self._previews: dict[str, _PreviewState] = {}
        self._tokens: dict[str, _TokenState] = {}
        self._attestation_records: dict[str, str] = {}
        self._audit: list[AuditEvent] = []

    def _now(self) -> datetime:
        result = _as_utc(self._clock())
        if self._last_clock_read is not None and result < self._last_clock_read:
            raise RecordStoreError("store clock moved backward")
        self._last_clock_read = result
        return result

    @property
    def audit_events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._audit)

    def read(self, record_id: str, revision_id: str | None = None) -> RecordSnapshot:
        with self._lock:
            return self._read_unlocked(record_id, revision_id)

    def _read_unlocked(
        self, record_id: str, revision_id: str | None = None
    ) -> RecordSnapshot:
        if revision_id is None:
            snapshot = self._current.get(record_id)
            if snapshot is None:
                raise RecordNotFound(record_id)
            return RecordSnapshot(record_id, snapshot.revision_id, deepcopy(snapshot.record))
        record = self._history.get(record_id, {}).get(revision_id)
        if record is None:
            raise RecordNotFound(f"{record_id}@{revision_id}")
        return RecordSnapshot(record_id, revision_id, deepcopy(record))

    def preview_upsert(
        self,
        proposed_record: dict[str, Any],
        purpose: str,
        *,
        preview_ttl_seconds: int = 900,
    ) -> ChangePreview:
        with self._lock:
            return self._preview_upsert_unlocked(
                proposed_record, purpose, preview_ttl_seconds
            )

    def _preview_upsert_unlocked(
        self,
        proposed_record: dict[str, Any],
        purpose: str,
        preview_ttl_seconds: int,
    ) -> ChangePreview:
        created = self._now()
        self._purge_expired_unlocked(created)
        candidate = deepcopy(proposed_record)
        errors = validate_record(candidate)
        if errors:
            raise InvalidRecord(errors)
        if candidate["memory_policy"] == "OFF":
            raise ConsentError("memory policy OFF forbids a record write")
        if not purpose.strip():
            raise ValueError("purpose is required")
        if not 1 <= preview_ttl_seconds <= 3600:
            raise ValueError("preview_ttl_seconds must be between 1 and 3600")

        record_id = candidate["record_id"]
        current = self._current.get(record_id)
        if current and _parse_timestamp(candidate["updated_at"]) <= _parse_timestamp(
            current.record["updated_at"]
        ):
            raise RevisionConflict("updated_at must advance beyond the current revision")
        before = current.record if current else _MISSING
        delta = tuple(_diff(before, candidate))
        if not delta:
            raise RecordStoreError("proposed record has no changes")

        operation: Operation = "UPDATE" if current else "CREATE"
        public = ChangePreview(
            preview_id="preview-" + secrets.token_hex(24),
            operation=operation,
            record_id=record_id,
            base_revision_id=current.revision_id if current else None,
            proposed_revision_id=_revision_id(),
            purpose=purpose,
            created_at=_timestamp(created),
            expires_at=_timestamp(created + timedelta(seconds=preview_ttl_seconds)),
            delta=delta,
        )
        self._previews[public.preview_id] = _PreviewState(deepcopy(public), candidate)
        return deepcopy(public)

    def preview_correction(
        self,
        record_id: str,
        *,
        correction_id: str,
        target_id: str,
        replacement_or_action: str,
        purpose: str,
    ) -> ChangePreview:
        with self._lock:
            current = self._read_unlocked(record_id).record
            if any(
                item.get("id") == correction_id
                for collection in COLLECTIONS
                for item in current.get(collection, [])
                if isinstance(item, dict)
            ):
                raise RecordStoreError(f"duplicate correction id {correction_id}")

            target: tuple[str, dict[str, Any]] | None = None
            for collection in COLLECTIONS:
                for item in current.get(collection, []):
                    if isinstance(item, dict) and item.get("id") == target_id:
                        target = (collection, item)
                        break
                if target:
                    break
            if target is None:
                raise RecordStoreError(f"unknown correction target {target_id}")

            collection, item = target
            if collection == "preferences":
                item["superseded"] = True
            elif collection == "hypotheses":
                item["status"] = "superseded"
            else:
                raise RecordStoreError(
                    f"corrections for {collection} are unsupported until the schema "
                    "defines a non-ambiguous supersession operation"
                )

            timestamp = _timestamp(self._now())
            current["corrections"].append(
                {
                    "id": correction_id,
                    "target_id": target_id,
                    "replacement_or_action": replacement_or_action,
                    "recorded_at": timestamp,
                }
            )
            current["updated_at"] = timestamp
            return self._preview_upsert_unlocked(current, purpose, 900)

    def preview_delete(
        self,
        record_id: str,
        purpose: str,
        *,
        preview_ttl_seconds: int = 900,
    ) -> ChangePreview:
        with self._lock:
            created = self._now()
            self._purge_expired_unlocked(created)
            current = self._read_unlocked(record_id)
            if not purpose.strip():
                raise ValueError("purpose is required")
            if not 1 <= preview_ttl_seconds <= 3600:
                raise ValueError("preview_ttl_seconds must be between 1 and 3600")
            public = ChangePreview(
                preview_id="preview-" + secrets.token_hex(24),
                operation="DELETE",
                record_id=record_id,
                base_revision_id=current.revision_id,
                proposed_revision_id=None,
                purpose=purpose,
                created_at=_timestamp(created),
                expires_at=_timestamp(created + timedelta(seconds=preview_ttl_seconds)),
                delta=tuple(_diff(current.record, _MISSING)),
            )
            self._previews[public.preview_id] = _PreviewState(deepcopy(public), None)
            return deepcopy(public)

    def get_preview(self, preview_id: str) -> ChangePreview:
        with self._lock:
            self._purge_expired_unlocked(self._now())
            state = self._previews.get(preview_id)
            if state is None:
                raise RecordStoreError("unknown preview")
            return deepcopy(state.public)

    def issue_consent(
        self,
        preview_id: str,
        confirmation: HostUserConfirmation,
        *,
        ttl_seconds: int = 300,
    ) -> ConsentToken:
        with self._lock:
            issued = self._now()
            self._purge_expired_unlocked(issued)
            preview = self._previews.get(preview_id)
            if preview is None:
                raise ConsentError("preview is unknown or expired")
            if not 1 <= ttl_seconds <= 3600:
                raise ValueError("ttl_seconds must be between 1 and 3600")
            if confirmation.preview_id != preview_id:
                raise ConsentError("host confirmation is bound to another preview")
            if not _OPAQUE_ATTESTATION_ID.fullmatch(confirmation.attestation_id):
                raise ConsentError("host attestation id must be an opaque att_ identifier")
            if confirmation.attestation_id in self._attestation_records:
                raise ConsentError("host attestation was already used")
            try:
                confirmed_at = _parse_timestamp(confirmation.confirmed_at)
            except (TypeError, ValueError) as error:
                raise ConsentError("host confirmation has an invalid timestamp") from error
            if not _parse_timestamp(preview.public.created_at) <= confirmed_at <= issued:
                raise ConsentError("host confirmation time is outside the preview window")
            if issued >= _parse_timestamp(preview.public.expires_at):
                raise ConsentError("preview expired before consent")
            if any(
                state.public.preview_id == preview_id
                and not state.revoked
                and not state.consumed
                for state in self._tokens.values()
            ):
                raise ConsentError("preview already has an active consent token")
            try:
                verified = self._consent_verifier.verify(
                    confirmation, deepcopy(preview.public)
                )
            except Exception as error:
                raise ConsentError("host user-confirmation verifier failed") from error
            if not verified:
                raise ConsentError("host user-confirmation attestation was not verified")

            expires = min(
                issued + timedelta(seconds=ttl_seconds),
                _parse_timestamp(preview.public.expires_at),
            )
            token = ConsentToken(
                token_id="consent-" + secrets.token_hex(24),
                preview_id=preview_id,
                attestation_id=confirmation.attestation_id,
                issued_at=_timestamp(issued),
                expires_at=_timestamp(expires),
            )
            self._tokens[token.token_id] = _TokenState(token, preview.public.record_id)
            self._attestation_records[confirmation.attestation_id] = (
                preview.public.record_id
            )
            return token

    def revoke_consent(self, token_id: str) -> RevocationResult:
        with self._lock:
            token = self._tokens.get(token_id)
            if token is None:
                raise ConsentError("unknown consent token")
            if token.consumed:
                return RevocationResult("already-consumed", token_id)
            if token.revoked:
                return RevocationResult("already-revoked", token_id)
            preview_id = token.public.preview_id
            family = [
                key
                for key, state in self._tokens.items()
                if state.public.preview_id == preview_id
            ]
            for key in family:
                state = self._tokens.pop(key)
                self._attestation_records.pop(state.public.attestation_id, None)
            self._previews.pop(preview_id, None)
            return RevocationResult("revoked", token_id)

    def commit(self, preview_id: str, token_id: str) -> CommitResult:
        with self._lock:
            preview, token, timestamp = self._authorize_unlocked(preview_id, token_id)
            public = preview.public
            if public.operation == "DELETE":
                raise RecordStoreError("use delete() for a deletion preview")
            candidate = deepcopy(preview.proposed_record)
            if candidate is None:
                raise RecordStoreError("upsert preview lacks proposed record")
            errors = validate_record(candidate)
            if errors:
                raise InvalidRecord(errors)
            self._check_base_revision_unlocked(public)

            snapshot = RecordSnapshot(
                public.record_id, public.proposed_revision_id or "", candidate
            )
            audit = self._make_audit(public, token.public, timestamp, "committed")
            new_current = dict(self._current)
            new_current[public.record_id] = snapshot
            new_history = deepcopy(self._history)
            new_history.setdefault(public.record_id, {})[snapshot.revision_id] = deepcopy(
                candidate
            )
            new_previews = {
                key: value
                for key, value in self._previews.items()
                if value.public.record_id != public.record_id
            }
            new_tokens = {
                key: value
                for key, value in self._tokens.items()
                if value.record_id != public.record_id
            }
            new_attestations = {
                key: value
                for key, value in self._attestation_records.items()
                if value != public.record_id
            }
            new_audit = [*self._audit, audit]

            self._current = new_current
            self._history = new_history
            self._previews = new_previews
            self._tokens = new_tokens
            self._attestation_records = new_attestations
            self._audit = new_audit
            return CommitResult(
                status="committed",
                operation=public.operation,
                record_id=public.record_id,
                revision_id=snapshot.revision_id,
                audit_event_id=audit.event_id,
            )

    def export(self, record_id: str) -> ExportResult:
        snapshot = self.read(record_id)
        return ExportResult(
            record_id=record_id,
            revision_id=snapshot.revision_id,
            content_sha256=_digest(snapshot.record),
            record=snapshot.record,
        )

    def delete(self, preview_id: str, token_id: str) -> DeletionResult:
        with self._lock:
            preview, token, timestamp = self._authorize_unlocked(preview_id, token_id)
            public = preview.public
            if public.operation != "DELETE":
                raise RecordStoreError("delete() requires a deletion preview")
            self._check_base_revision_unlocked(public)
            revision_count = len(self._history.get(public.record_id, {}))
            preview_count = sum(
                state.public.record_id == public.record_id
                for state in self._previews.values()
            )
            audit = self._make_audit(public, token.public, timestamp, "deleted")
            new_current = dict(self._current)
            new_current.pop(public.record_id, None)
            new_history = deepcopy(self._history)
            new_history.pop(public.record_id, None)
            new_previews = {
                key: value
                for key, value in self._previews.items()
                if value.public.record_id != public.record_id
            }
            new_tokens = {
                key: value
                for key, value in self._tokens.items()
                if value.record_id != public.record_id
            }
            new_attestations = {
                key: value
                for key, value in self._attestation_records.items()
                if value != public.record_id
            }
            new_audit = [*self._audit, audit]

            self._current = new_current
            self._history = new_history
            self._previews = new_previews
            self._tokens = new_tokens
            self._attestation_records = new_attestations
            self._audit = new_audit
            inventory = self._retention_inventory_unlocked(public.record_id)
            return DeletionResult(
                status="deleted",
                record_id=public.record_id,
                content_revisions_deleted=revision_count,
                pending_previews_deleted=preview_count,
                record_present_after=public.record_id in self._current,
                content_present_after=any(
                    inventory[key]
                    for key in ("current", "revisions", "pending_previews")
                ),
                audit_metadata_retained=inventory["audit_events"] > 0,
                retained_audit_events=inventory["audit_events"],
                audit_event_id=audit.event_id,
            )

    def _authorize_unlocked(
        self, preview_id: str, token_id: str
    ) -> tuple[_PreviewState, _TokenState, datetime]:
        timestamp = self._now()
        self._purge_expired_unlocked(timestamp)
        preview = self._previews.get(preview_id)
        token = self._tokens.get(token_id)
        if preview is None:
            raise ConsentError("preview is unknown or expired")
        if token is None or token.public.preview_id != preview_id:
            raise ConsentError("consent token is missing or bound to another preview")
        if token.revoked:
            raise ConsentError("consent token was revoked")
        if token.consumed:
            raise ConsentError("consent token was already consumed")
        if timestamp >= _parse_timestamp(preview.public.expires_at):
            raise ConsentError("preview expired")
        if timestamp >= _parse_timestamp(token.public.expires_at):
            raise ConsentError("consent token expired")
        return preview, token, timestamp

    def content_inventory(self, record_id: str) -> dict[str, int]:
        """Return content-bearing locations for deletion conformance checks."""

        with self._lock:
            return self._content_inventory_unlocked(record_id)

    def _content_inventory_unlocked(self, record_id: str) -> dict[str, int]:
        return {
            "current": int(record_id in self._current),
            "revisions": len(self._history.get(record_id, {})),
            "pending_previews": sum(
                state.public.record_id == record_id
                for state in self._previews.values()
            ),
        }

    def retention_inventory(self, record_id: str) -> dict[str, int]:
        """Return every record-associated content and metadata location."""

        with self._lock:
            return self._retention_inventory_unlocked(record_id)

    def _retention_inventory_unlocked(self, record_id: str) -> dict[str, int]:
        result = self._content_inventory_unlocked(record_id)
        result.update(
            {
                "tokens": sum(
                    state.record_id == record_id for state in self._tokens.values()
                ),
                "attestations": sum(
                    value == record_id for value in self._attestation_records.values()
                ),
                "audit_events": sum(
                    event.record_id == record_id for event in self._audit
                ),
            }
        )
        return result

    def _purge_expired_unlocked(self, now: datetime) -> None:
        expired_previews = {
            preview_id
            for preview_id, state in self._previews.items()
            if now >= _parse_timestamp(state.public.expires_at)
        }
        for preview_id in expired_previews:
            self._previews.pop(preview_id, None)
        for token_id, state in list(self._tokens.items()):
            preview_expired = state.public.preview_id in expired_previews
            token_expired = now >= _parse_timestamp(state.public.expires_at)
            if preview_expired or token_expired:
                self._tokens.pop(token_id, None)
                if preview_expired:
                    self._attestation_records.pop(state.public.attestation_id, None)

    def _check_base_revision_unlocked(self, preview: ChangePreview) -> None:
        current = self._current.get(preview.record_id)
        current_revision = current.revision_id if current else None
        if current_revision != preview.base_revision_id:
            raise RevisionConflict(
                f"expected base {preview.base_revision_id}, found {current_revision}"
            )

    def _make_audit(
        self,
        preview: ChangePreview,
        token: ConsentToken,
        timestamp: datetime,
        result: Literal["committed", "deleted"],
    ) -> AuditEvent:
        return AuditEvent(
            event_id="audit-" + secrets.token_hex(16),
            record_id=preview.record_id,
            revision_before=preview.base_revision_id,
            revision_after=preview.proposed_revision_id,
            operation=preview.operation,
            field_paths=tuple(entry.path for entry in preview.delta),
            consent_token_id=token.token_id,
            timestamp=_timestamp(timestamp),
            result=result,
        )
