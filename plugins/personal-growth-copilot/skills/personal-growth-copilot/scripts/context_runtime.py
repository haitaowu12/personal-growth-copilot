#!/usr/bin/env python3
"""Executable controls for inquiry materiality, user scoring, and decisions.

This module is deliberately host-neutral and non-persistent. It prevents a
model from treating questions, scores, or a dossier as unconstrained prose.
Persistent writes still require ``record_store.py`` and its host-attested
preview/token/commit boundary.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock, RLock
from typing import Callable, Protocol


ALLOWED_MODES = {"QUICK", "DIALOGUE", "DEEP_CONTEXT", "REVIEW"}
ALLOWED_CHANGES = {
    "recommendation",
    "hypothesis",
    "safety_route",
    "experiment",
    "support_need",
}
ATTESTATION_PATTERN = re.compile(r"^att_[0-9a-f]{32}$")


class ContextRuntimeError(RuntimeError):
    pass


class ConsentError(ContextRuntimeError):
    pass


class QuestionError(ContextRuntimeError):
    pass


class ScaleError(ContextRuntimeError):
    pass


class DecisionError(ContextRuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContextRuntimeError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class InquiryConsentAttestation:
    attestation_id: str
    scope: str
    confirmed_at: str


class InquiryConsentVerifier(Protocol):
    def verify(self, attestation: InquiryConsentAttestation) -> bool: ...


@dataclass(frozen=True)
class QuestionClassificationAttestation:
    attestation_id: str
    question_sha256: str
    sensitivity: str
    materiality_verified: bool
    consent_scope_sha256: str | None
    classified_at: str


class QuestionClassificationVerifier(Protocol):
    def verify(self, attestation: QuestionClassificationAttestation) -> bool: ...


@dataclass(frozen=True)
class HostUserActionAttestation:
    attestation_id: str
    action: str
    payload_sha256: str
    confirmed_at: str


class UserActionVerifier(Protocol):
    def verify(self, attestation: HostUserActionAttestation) -> bool: ...


class UserActionGate:
    """Verify and consume exact user actions once within a host session."""

    def __init__(self, verifier: UserActionVerifier) -> None:
        self._verifier = verifier
        self._used_attestations: set[str] = set()
        self._lock = Lock()

    def require(
        self,
        *,
        action: str,
        payload: dict[str, object],
        attestation: HostUserActionAttestation,
        at: datetime,
    ) -> None:
        with self._lock:
            if attestation.attestation_id in self._used_attestations:
                raise ConsentError("user-action attestation is single use")
            _verify_user_action(
                action=action,
                payload=payload,
                attestation=attestation,
                verifier=self._verifier,
                at=at,
            )
            self._used_attestations.add(attestation.attestation_id)


@dataclass(frozen=True)
class ModelDeltaAttestation:
    attestation_id: str
    question_id: str
    changed_fields: tuple[str, ...]
    previous_model_sha256: str
    updated_model_sha256: str
    observed_at: str


class ModelDeltaVerifier(Protocol):
    def verify(self, attestation: ModelDeltaAttestation) -> bool: ...


@dataclass(frozen=True)
class MaterialQuestion:
    question_id: str
    text: str
    rationale: str
    would_change: tuple[str, ...]
    offers_skip: bool = False


@dataclass(frozen=True)
class QuestionDecision:
    status: str
    reason: str


@dataclass(frozen=True)
class ContextEvent:
    sequence: int
    rule_id: str
    event: str
    timestamp: str
    detail: str


@dataclass(frozen=True)
class ScaleDefinition:
    scale_id: str
    construct: str
    minimum: float
    maximum: float
    low_anchor: str
    high_anchor: str
    purpose: str
    decision_link: str
    context_boundary: str
    created_at: str
    review_at: str
    status: str = "active"


@dataclass(frozen=True)
class CheckIn:
    checkin_id: str
    scale_id: str
    value: float
    user_supplied: bool
    recorded_at: str
    context: str
    decision_link: str


@dataclass(frozen=True)
class DecisionOption:
    option_id: str
    label: str
    benefit: str
    cost: str
    reversibility: str


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    question: str
    options: tuple[DecisionOption, ...]
    selected_option_id: str
    chosen_by: str
    rationale: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    created_at: str
    review_at: str | None = None
    recommended_option_id: str | None = None


class ContextSession:
    """Track consent and inquiry saturation without storing user content."""

    def __init__(
        self,
        *,
        consent_verifier: InquiryConsentVerifier,
        question_classification_verifier: QuestionClassificationVerifier,
        model_delta_verifier: ModelDeltaVerifier,
        clock: Callable[[], datetime],
        mode: str = "DIALOGUE",
    ) -> None:
        if not isinstance(mode, str) or mode not in ALLOWED_MODES:
            raise ContextRuntimeError(f"unsupported mode {mode}")
        self._consent_verifier = consent_verifier
        self._question_classification_verifier = question_classification_verifier
        self._model_delta_verifier = model_delta_verifier
        self._clock = clock
        self._lock = RLock()
        self._last_time = _utc(clock())
        self._mode = mode
        self._inquiry_scope: str | None = None
        self._used_attestations: set[str] = set()
        self._used_classification_attestations: set[str] = set()
        self._used_delta_attestations: set[str] = set()
        self._open_question: MaterialQuestion | None = None
        self._open_question_requires_consent = False
        self._unchanged_answers = 0
        self._saturated = False
        self._history: list[ContextEvent] = []

    @property
    def inquiry_consent_active(self) -> bool:
        return self._inquiry_scope is not None

    @property
    def inquiry_scope(self) -> str | None:
        return self._inquiry_scope

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def saturated(self) -> bool:
        return self._saturated

    @property
    def history(self) -> tuple[ContextEvent, ...]:
        return tuple(self._history)

    @property
    def open_question_id(self) -> str | None:
        return self._open_question.question_id if self._open_question else None

    def _now(self) -> datetime:
        current = _utc(self._clock())
        if current < self._last_time:
            raise ContextRuntimeError("clock moved backward")
        return current

    def _append(self, rule_id: str, event: str, detail: str, now: datetime) -> None:
        self._history.append(
            ContextEvent(
                sequence=len(self._history) + 1,
                rule_id=rule_id,
                event=event,
                timestamp=_timestamp(now),
                detail=detail,
            )
        )
        self._last_time = now

    def grant_inquiry_consent(self, attestation: InquiryConsentAttestation) -> None:
        with self._lock:
            self._grant_inquiry_consent(attestation)

    def _grant_inquiry_consent(self, attestation: InquiryConsentAttestation) -> None:
        now = self._now()
        if not isinstance(attestation, InquiryConsentAttestation):
            raise ConsentError("host consent attestation has the wrong type")
        if not isinstance(attestation.attestation_id, str) or not ATTESTATION_PATTERN.fullmatch(
            attestation.attestation_id
        ):
            raise ConsentError("malformed host attestation id")
        if not isinstance(attestation.scope, str) or not attestation.scope.strip():
            raise ConsentError("inquiry consent requires a bounded scope")
        if not isinstance(attestation.confirmed_at, str):
            raise ConsentError("invalid confirmation timestamp")
        try:
            confirmed = _utc(
                datetime.fromisoformat(attestation.confirmed_at.replace("Z", "+00:00"))
            )
        except (TypeError, ValueError) as exc:
            raise ConsentError("invalid confirmation timestamp") from exc
        if confirmed > now:
            raise ConsentError("confirmation timestamp is in the future")
        if attestation.attestation_id in self._used_attestations:
            raise ConsentError("host attestation is single use")
        if not self._consent_verifier.verify(attestation):
            raise ConsentError("host did not verify affirmative user consent")
        event = ContextEvent(
            sequence=len(self._history) + 1,
            rule_id="PGC-CTX-01",
            event="INQUIRY_CONSENT_GRANTED",
            timestamp=_timestamp(now),
            detail="bounded scope accepted",
        )
        self._inquiry_scope = attestation.scope
        self._used_attestations.add(attestation.attestation_id)
        self._history.append(event)
        self._last_time = now

    def revoke_inquiry_consent(self) -> None:
        with self._lock:
            self._revoke_inquiry_consent()

    def _revoke_inquiry_consent(self) -> None:
        now = self._now()
        self._inquiry_scope = None
        if self._open_question and self._open_question_requires_consent:
            self._open_question = None
            self._open_question_requires_consent = False
        self._append("PGC-CTX-02", "INQUIRY_CONSENT_REVOKED", "effective immediately", now)

    def propose_question(
        self,
        question: MaterialQuestion,
        *,
        classification: QuestionClassificationAttestation,
    ) -> QuestionDecision:
        with self._lock:
            return self._propose_question(question, classification=classification)

    def _propose_question(
        self,
        question: MaterialQuestion,
        *,
        classification: QuestionClassificationAttestation,
    ) -> QuestionDecision:
        now = self._now()
        if not isinstance(question, MaterialQuestion) or not isinstance(
            classification, QuestionClassificationAttestation
        ):
            raise QuestionError("question and classification have the wrong type")
        if (
            not isinstance(question.question_id, str)
            or not question.question_id.strip()
            or not isinstance(question.text, str)
            or not isinstance(question.rationale, str)
            or not isinstance(question.would_change, tuple)
            or not all(isinstance(item, str) for item in question.would_change)
            or not isinstance(question.offers_skip, bool)
        ):
            raise QuestionError("material question fields are malformed")
        if (
            not isinstance(classification.attestation_id, str)
            or not isinstance(classification.question_sha256, str)
            or not isinstance(classification.sensitivity, str)
            or not isinstance(classification.materiality_verified, bool)
            or (
                classification.consent_scope_sha256 is not None
                and not isinstance(classification.consent_scope_sha256, str)
            )
            or not isinstance(classification.classified_at, str)
        ):
            raise QuestionError("question classification fields are malformed")
        if self._saturated:
            return QuestionDecision(
                "SATURATED", "summarize the working model and offer action or stopping"
            )
        if self._open_question is not None:
            raise QuestionError("only one unanswered material question is allowed")
        changes = set(question.would_change)
        if not changes or not changes.issubset(ALLOWED_CHANGES):
            return QuestionDecision(
                "REJECTED", "no valid consequential decision link was declared"
            )
        if not question.text.strip() or not question.rationale.strip():
            return QuestionDecision("REJECTED", "question and rationale are required")
        if not ATTESTATION_PATTERN.fullmatch(classification.attestation_id):
            raise QuestionError("malformed question-classification attestation id")
        if classification.attestation_id in self._used_classification_attestations:
            raise QuestionError("question-classification attestation is single use")
        if classification.question_sha256 != _question_sha256(question):
            raise QuestionError("question classification is bound to another question")
        if classification.sensitivity not in {"ordinary", "sensitive"}:
            raise QuestionError("host returned an unknown sensitivity class")
        if classification.materiality_verified is not True:
            return QuestionDecision(
                "REJECTED", "host did not verify a consequential decision link"
            )
        try:
            classified = _utc(
                datetime.fromisoformat(classification.classified_at.replace("Z", "+00:00"))
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise QuestionError("question classification timestamp is invalid") from exc
        if classified > now:
            raise QuestionError("question classification timestamp is in the future")
        if not self._question_classification_verifier.verify(classification):
            raise QuestionError("host did not verify the exact question classification")
        self._used_classification_attestations.add(classification.attestation_id)
        requires_consent = (
            classification.sensitivity == "sensitive" or self.mode == "DEEP_CONTEXT"
        )
        if requires_consent:
            if not question.offers_skip:
                return QuestionDecision(
                    "REJECTED",
                    "sensitive or extended questions must explicitly offer skip or stop",
                )
            if not self.inquiry_consent_active:
                return QuestionDecision(
                    "CONSENT_REQUIRED", "obtain bounded host-verified inquiry consent"
                )
            if classification.consent_scope_sha256 != _scope_sha256(self._inquiry_scope):
                return QuestionDecision(
                    "CONSENT_REQUIRED",
                    "question classification is not bound to the active consent scope",
                )
        elif classification.consent_scope_sha256 is not None:
            raise QuestionError("ordinary classification may not claim a consent scope")
        self._open_question = question
        self._open_question_requires_consent = requires_consent
        self._append(
            "PGC-CTX-03",
            "MATERIAL_QUESTION_OPENED",
            ",".join(sorted(changes)),
            now,
        )
        return QuestionDecision("ALLOWED", "one material question is open")

    def resolve_question(
        self,
        question_id: str,
        *,
        model_delta: ModelDeltaAttestation | None,
    ) -> str:
        with self._lock:
            return self._resolve_question(question_id, model_delta=model_delta)

    def _resolve_question(
        self,
        question_id: str,
        *,
        model_delta: ModelDeltaAttestation | None,
    ) -> str:
        now = self._now()
        if not isinstance(question_id, str) or not question_id.strip():
            raise QuestionError("question id is malformed")
        if self._open_question is None or self._open_question.question_id != question_id:
            raise QuestionError("question is not the current open question")
        model_changed = False
        changed_fields: tuple[str, ...] = ()
        if model_delta is not None:
            if not isinstance(model_delta, ModelDeltaAttestation):
                raise QuestionError("model-delta attestation has the wrong type")
            if (
                not isinstance(model_delta.attestation_id, str)
                or not isinstance(model_delta.question_id, str)
                or not isinstance(model_delta.changed_fields, tuple)
                or not all(isinstance(item, str) for item in model_delta.changed_fields)
                or not isinstance(model_delta.previous_model_sha256, str)
                or not isinstance(model_delta.updated_model_sha256, str)
                or not isinstance(model_delta.observed_at, str)
            ):
                raise QuestionError("model-delta attestation fields are malformed")
            if not ATTESTATION_PATTERN.fullmatch(model_delta.attestation_id):
                raise QuestionError("malformed model-delta attestation id")
            if model_delta.attestation_id in self._used_delta_attestations:
                raise QuestionError("model-delta attestation is single use")
            if model_delta.question_id != question_id:
                raise QuestionError("model-delta attestation is bound to another question")
            changed_fields = tuple(dict.fromkeys(model_delta.changed_fields))
            if not changed_fields or not set(changed_fields).issubset(ALLOWED_CHANGES):
                raise QuestionError("model delta has no allowed consequential field")
            if not set(changed_fields).issubset(self._open_question.would_change):
                raise QuestionError(
                    "model delta is not bound to the question's declared decision link"
                )
            if (
                not re.fullmatch(r"[0-9a-f]{64}", model_delta.previous_model_sha256)
                or not re.fullmatch(r"[0-9a-f]{64}", model_delta.updated_model_sha256)
                or model_delta.previous_model_sha256 == model_delta.updated_model_sha256
            ):
                raise QuestionError("model delta hashes are invalid or unchanged")
            try:
                observed = _utc(
                    datetime.fromisoformat(model_delta.observed_at.replace("Z", "+00:00"))
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise QuestionError("model delta timestamp is invalid") from exc
            if observed > now:
                raise QuestionError("model delta timestamp is in the future")
            if not self._model_delta_verifier.verify(model_delta):
                raise QuestionError("host did not verify the visible model delta")
            self._used_delta_attestations.add(model_delta.attestation_id)
            model_changed = True
        self._open_question = None
        self._open_question_requires_consent = False
        self._unchanged_answers = 0 if model_changed else self._unchanged_answers + 1
        self._saturated = self._unchanged_answers >= 2
        next_action = (
            "SUMMARIZE_AND_OFFER_ACTION"
            if self._saturated
            else "MAY_ASK_NEXT_MATERIAL_QUESTION"
        )
        self._append(
            "PGC-CTX-04",
            "QUESTION_RESOLVED",
            f"model_changed={str(model_changed).lower()};fields={','.join(changed_fields)};next={next_action}",
            now,
        )
        return next_action


def _action_payload_sha256(action: str, payload: dict[str, object]) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(
            {"action": action, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _question_sha256(question: MaterialQuestion) -> str:
    return _action_payload_sha256(
        "CLASSIFY_QUESTION",
        {
            "question_id": question.question_id,
            "text": question.text,
            "rationale": question.rationale,
            "would_change": list(question.would_change),
            "offers_skip": question.offers_skip,
        },
    )


def _scope_sha256(scope: str | None) -> str | None:
    if scope is None:
        return None
    return _action_payload_sha256("INQUIRY_SCOPE", {"scope": scope})


def _verify_user_action(
    *,
    action: str,
    payload: dict[str, object],
    attestation: HostUserActionAttestation,
    verifier: UserActionVerifier,
    at: datetime,
) -> None:
    if not isinstance(attestation, HostUserActionAttestation):
        raise ConsentError("user-action attestation has the wrong type")
    if (
        not isinstance(attestation.attestation_id, str)
        or not isinstance(attestation.action, str)
        or not isinstance(attestation.payload_sha256, str)
        or not isinstance(attestation.confirmed_at, str)
    ):
        raise ConsentError("user-action attestation fields are malformed")
    if not ATTESTATION_PATTERN.fullmatch(attestation.attestation_id):
        raise ConsentError("malformed user-action attestation id")
    if attestation.action != action:
        raise ConsentError("user-action attestation has the wrong action")
    if attestation.payload_sha256 != _action_payload_sha256(action, payload):
        raise ConsentError("user-action attestation is bound to another payload")
    try:
        confirmed = _utc(
            datetime.fromisoformat(attestation.confirmed_at.replace("Z", "+00:00"))
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ConsentError("user-action confirmation timestamp is invalid") from exc
    if confirmed > _utc(at):
        raise ConsentError("user-action confirmation timestamp is in the future")
    if not verifier.verify(attestation):
        raise ConsentError("host did not verify the user's exact action")


def define_scale(
    *,
    scale_id: str,
    construct: str,
    minimum: float,
    maximum: float,
    low_anchor: str,
    high_anchor: str,
    purpose: str,
    decision_link: str,
    context_boundary: str,
    created_at: datetime,
    review_at: datetime,
    attestation: HostUserActionAttestation,
    user_action_gate: UserActionGate,
) -> ScaleDefinition:
    string_fields = (
            scale_id,
            construct,
            low_anchor,
            high_anchor,
            purpose,
            decision_link,
            context_boundary,
    )
    if not all(isinstance(value, str) and value.strip() for value in string_fields):
        raise ScaleError("scale fields must be non-empty")
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not isinstance(
        maximum, (int, float)
    ) or isinstance(maximum, bool):
        raise ScaleError("scale bounds must be numeric")
    if minimum >= maximum:
        raise ScaleError("minimum must be below maximum")
    if not math.isfinite(float(minimum)) or not math.isfinite(float(maximum)):
        raise ScaleError("scale bounds must be finite")
    if low_anchor.strip() == high_anchor.strip():
        raise ScaleError("scale anchors must be distinct")
    try:
        created = _utc(created_at)
        review = _utc(review_at)
    except ContextRuntimeError as exc:
        raise ScaleError("scale timestamps must be timezone aware") from exc
    if review <= created:
        raise ScaleError("review_at must be after created_at")
    approval_payload: dict[str, object] = {
        "scale_id": scale_id,
        "construct": construct,
        "minimum": float(minimum),
        "maximum": float(maximum),
        "low_anchor": low_anchor,
        "high_anchor": high_anchor,
        "purpose": purpose,
        "decision_link": decision_link,
        "context_boundary": context_boundary,
        "created_at": _timestamp(created),
        "review_at": _timestamp(review),
    }
    try:
        user_action_gate.require(
            action="DEFINE_SCALE",
            payload=approval_payload,
            attestation=attestation,
            at=created,
        )
    except ConsentError as exc:
        raise ScaleError(str(exc)) from exc
    return ScaleDefinition(
        scale_id=scale_id,
        construct=construct,
        minimum=float(minimum),
        maximum=float(maximum),
        low_anchor=low_anchor,
        high_anchor=high_anchor,
        purpose=purpose,
        decision_link=decision_link,
        context_boundary=context_boundary,
        created_at=_timestamp(created),
        review_at=_timestamp(review),
    )


def record_check_in(
    *,
    scale: ScaleDefinition,
    checkin_id: str,
    value: float,
    recorded_at: datetime,
    context: str,
    decision_link: str,
    attestation: HostUserActionAttestation,
    user_action_gate: UserActionGate,
) -> CheckIn:
    if not isinstance(scale, ScaleDefinition):
        raise ScaleError("scale has the wrong type")
    if scale.status != "active":
        raise ScaleError("the scale is not active")
    try:
        recorded = _utc(recorded_at)
    except ContextRuntimeError as exc:
        raise ScaleError("check-in timestamp must be timezone aware") from exc
    if not _utc(datetime.fromisoformat(scale.created_at.replace("Z", "+00:00"))) <= recorded:
        raise ScaleError("check-in precedes scale creation")
    if recorded >= _utc(datetime.fromisoformat(scale.review_at.replace("Z", "+00:00"))):
        raise ScaleError("the scale definition is due for review")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ScaleError("check-in value must be numeric")
    if not scale.minimum <= value <= scale.maximum:
        raise ScaleError("value is outside the user-approved scale")
    if not math.isfinite(float(value)):
        raise ScaleError("check-in value must be finite")
    if not all(
        isinstance(item, str) and item.strip()
        for item in (checkin_id, context, decision_link)
    ):
        raise ScaleError("check-in id, context, and decision link are required")
    if decision_link != scale.decision_link:
        raise ScaleError("check-in decision link differs from the approved scale")
    checkin_payload: dict[str, object] = {
        "checkin_id": checkin_id,
        "scale_id": scale.scale_id,
        "value": float(value),
        "recorded_at": _timestamp(recorded),
        "context": context,
        "decision_link": decision_link,
    }
    try:
        user_action_gate.require(
            action="ENTER_SCORE",
            payload=checkin_payload,
            attestation=attestation,
            at=recorded,
        )
    except ConsentError as exc:
        raise ScaleError(str(exc)) from exc
    return CheckIn(
        checkin_id=checkin_id,
        scale_id=scale.scale_id,
        value=float(value),
        user_supplied=True,
        recorded_at=_timestamp(recorded),
        context=context,
        decision_link=decision_link,
    )


def pause_scale_for_fixation(scale: ScaleDefinition) -> ScaleDefinition:
    return replace(scale, status="paused")


def record_user_decision(
    *,
    decision_id: str,
    question: str,
    options: tuple[DecisionOption, ...],
    selected_option_id: str,
    chosen_by: str,
    rationale: str,
    evidence_ids: tuple[str, ...],
    assumptions: tuple[str, ...],
    unknowns: tuple[str, ...],
    created_at: datetime,
    review_at: datetime | None = None,
    recommended_option_id: str | None = None,
    attestation: HostUserActionAttestation,
    user_action_gate: UserActionGate,
) -> DecisionRecord:
    if not isinstance(options, tuple) or not all(
        isinstance(option, DecisionOption) for option in options
    ):
        raise DecisionError("decision options have the wrong type")
    if not all(
        isinstance(item, str)
        for item in (
            decision_id,
            question,
            selected_option_id,
            chosen_by,
            rationale,
        )
    ):
        raise DecisionError("decision fields have the wrong type")
    if not all(
        isinstance(items, tuple) and all(isinstance(item, str) for item in items)
        for items in (evidence_ids, assumptions, unknowns)
    ):
        raise DecisionError("decision reference fields have the wrong type")
    if chosen_by != "USER":
        raise DecisionError("only the user may choose a personal-growth option")
    if not decision_id.strip() or not question.strip() or not rationale.strip():
        raise DecisionError("decision id, question, and rationale are required")
    if not 2 <= len(options) <= 5:
        raise DecisionError("a decision requires two through five viable options")
    if any(
        not isinstance(value, str) or not value.strip()
        for option in options
        for value in (
            option.option_id,
            option.label,
            option.benefit,
            option.cost,
            option.reversibility,
        )
    ):
        raise DecisionError("every option field must be non-empty")
    option_ids = [option.option_id for option in options]
    if len(option_ids) != len(set(option_ids)):
        raise DecisionError("option ids must be unique")
    if selected_option_id not in option_ids:
        raise DecisionError("selected option is absent")
    if recommended_option_id is not None and recommended_option_id not in option_ids:
        raise DecisionError("recommended option is absent")
    if any(option.reversibility not in {"high", "medium", "low"} for option in options):
        raise DecisionError("invalid reversibility")
    try:
        created = _utc(created_at)
    except ContextRuntimeError as exc:
        raise DecisionError("decision created_at must be timezone aware") from exc
    if review_at is None:
        raise DecisionError("a chosen decision requires a review point")
    try:
        review = _utc(review_at)
    except ContextRuntimeError as exc:
        raise DecisionError("decision review_at must be timezone aware") from exc
    if review <= created:
        raise DecisionError("review_at must be after created_at")
    decision_payload: dict[str, object] = {
        "decision_id": decision_id,
        "question": question,
        "options": [
            {
                "option_id": option.option_id,
                "label": option.label,
                "benefit": option.benefit,
                "cost": option.cost,
                "reversibility": option.reversibility,
            }
            for option in options
        ],
        "selected_option_id": selected_option_id,
        "created_at": _timestamp(created),
    }
    try:
        user_action_gate.require(
            action="CHOOSE_OPTION",
            payload=decision_payload,
            attestation=attestation,
            at=created,
        )
    except ConsentError as exc:
        raise DecisionError(str(exc)) from exc
    return DecisionRecord(
        decision_id=decision_id,
        question=question,
        options=options,
        selected_option_id=selected_option_id,
        chosen_by="USER",
        rationale=rationale,
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        assumptions=assumptions,
        unknowns=unknowns,
        created_at=_timestamp(created),
        review_at=_timestamp(review),
        recommended_option_id=recommended_option_id,
    )
