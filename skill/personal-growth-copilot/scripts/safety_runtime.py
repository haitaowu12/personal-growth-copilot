#!/usr/bin/env python3
"""Executable safety-state and current-resource conformance controls.

The caller supplies risk observations and a trusted host resource resolver. The
module does not classify free text, provide emergency care, or contain a static
resource directory. It makes state, memory restrictions, resolver outcomes,
and invalid transitions observable to evaluation and host adapters.
"""

from __future__ import annotations

import re
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MACHINE = ROOT / "safety/safety-state-machine.yaml"

SafetyState = Literal[
    "ORDINARY_COACHING",
    "SCOPE_BOUNDARY",
    "SIGNIFICANT_IMPAIRMENT",
    "ACUTE_DANGER",
    "POST_CRISIS_RETURN",
]
ResolutionStatus = Literal["VERIFIED", "LOCATION_REQUIRED", "UNAVAILABLE"]
Clock = Callable[[], datetime]

REQUIRED_STATES = {
    "ORDINARY_COACHING",
    "SCOPE_BOUNDARY",
    "SIGNIFICANT_IMPAIRMENT",
    "ACUTE_DANGER",
    "POST_CRISIS_RETURN",
}
EXPECTED_STATE_CONTROLS = {
    "ORDINARY_COACHING": (True, True, "NONE"),
    "SCOPE_BOUNDARY": (False, False, "SAFE_ADJACENT_ONLY"),
    "SIGNIFICANT_IMPAIRMENT": (False, False, "QUALIFIED_SUPPORT"),
    "ACUTE_DANGER": (False, False, "CURRENT_OR_FALLBACK"),
    "POST_CRISIS_RETURN": (False, False, "BOUNDED_SUPPORT_ONLY"),
}
EXPECTED_TRANSITIONS = {
    ("ORDINARY_COACHING", "OUT_OF_SCOPE_REQUEST"): ("SAFE-TRANS-001", "SCOPE_BOUNDARY", (), ()),
    ("ORDINARY_COACHING", "SIGNIFICANT_IMPAIRMENT_SIGNAL"): ("SAFE-TRANS-002", "SIGNIFICANT_IMPAIRMENT", (), ()),
    ("ORDINARY_COACHING", "INDIRECT_ACUTE_RISK_SIGNAL"): ("SAFE-TRANS-003", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("ORDINARY_COACHING", "ACUTE_DANGER_SIGNAL"): ("SAFE-TRANS-004", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("SCOPE_BOUNDARY", "SAFE_ADJACENT_TASK_ACCEPTED"): ("SAFE-TRANS-005", "ORDINARY_COACHING", (), ()),
    ("SCOPE_BOUNDARY", "SIGNIFICANT_IMPAIRMENT_SIGNAL"): ("SAFE-TRANS-006", "SIGNIFICANT_IMPAIRMENT", (), ()),
    ("SCOPE_BOUNDARY", "INDIRECT_ACUTE_RISK_SIGNAL"): ("SAFE-TRANS-007", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("SCOPE_BOUNDARY", "ACUTE_DANGER_SIGNAL"): ("SAFE-TRANS-008", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("SIGNIFICANT_IMPAIRMENT", "BOUNDED_SUPPORT_PLAN_CONFIRMED"): ("SAFE-TRANS-009", "ORDINARY_COACHING", (), ()),
    ("SIGNIFICANT_IMPAIRMENT", "OUT_OF_SCOPE_REQUEST"): ("SAFE-TRANS-010", "SCOPE_BOUNDARY", (), ()),
    ("SIGNIFICANT_IMPAIRMENT", "INDIRECT_ACUTE_RISK_SIGNAL"): ("SAFE-TRANS-011", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("SIGNIFICANT_IMPAIRMENT", "ACUTE_DANGER_SIGNAL"): ("SAFE-TRANS-012", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("ACUTE_DANGER", "IMMEDIATE_SUPPORT_CONNECTED"): ("SAFE-TRANS-013", "ACUTE_DANGER", (), ("mark_support_connected",)),
    ("ACUTE_DANGER", "IMMEDIATE_DANGER_REDUCED"): ("SAFE-TRANS-014", "POST_CRISIS_RETURN", ("support_connected",), ()),
    ("ACUTE_DANGER", "ACUTE_DANGER_SIGNAL"): ("SAFE-TRANS-015", "ACUTE_DANGER", (), ()),
    ("POST_CRISIS_RETURN", "ACUTE_DANGER_SIGNAL"): ("SAFE-TRANS-016", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("POST_CRISIS_RETURN", "INDIRECT_ACUTE_RISK_SIGNAL"): ("SAFE-TRANS-017", "ACUTE_DANGER", (), ("freeze_memory", "clear_support")),
    ("POST_CRISIS_RETURN", "SAFE_RETURN_CONFIRMED"): ("SAFE-TRANS-018", "ORDINARY_COACHING", (), ()),
    ("ORDINARY_COACHING", "MEMORY_REENABLE_CONFIRMED"): ("SAFE-TRANS-019", "ORDINARY_COACHING", ("memory_latched",), ("thaw_memory",)),
}
REQUIRED_EVENTS = {
    "OUT_OF_SCOPE_REQUEST",
    "SIGNIFICANT_IMPAIRMENT_SIGNAL",
    "INDIRECT_ACUTE_RISK_SIGNAL",
    "ACUTE_DANGER_SIGNAL",
    "IMMEDIATE_SUPPORT_CONNECTED",
    "IMMEDIATE_DANGER_REDUCED",
    "SAFE_RETURN_CONFIRMED",
    "MEMORY_REENABLE_CONFIRMED",
}
RESTRICTED_STATES = REQUIRED_STATES - {"ORDINARY_COACHING"}
ALLOWED_EFFECTS = {
    "freeze_memory",
    "thaw_memory",
    "mark_support_connected",
    "clear_support",
}
ALLOWED_REQUIREMENTS = {"support_connected", "memory_latched"}
_RULE_ID = re.compile(r"^SAFE-TRANS-[0-9]{3}$")
_HTTPS_URI = re.compile(r"^https://[^\s]+$")
_RESOURCE_CHANNELS = {"phone", "text", "chat", "walk_in", "emergency_services"}


class SafetyRuntimeError(RuntimeError):
    """Base error for safety-control failures."""


class InvalidTransition(SafetyRuntimeError):
    pass


class SafetyGuardFailed(SafetyRuntimeError):
    pass


class RestrictedMemoryWrite(SafetyRuntimeError):
    pass


class ResourceResolutionError(SafetyRuntimeError):
    pass


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock and resource timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def load_machine(path: Path = DEFAULT_MACHINE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = validate_machine_spec(data)
    if errors:
        raise SafetyRuntimeError("invalid safety state machine: " + "; ".join(errors))
    return data


def validate_machine_spec(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["machine must be an object"]
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must equal 1.0")
    if data.get("initial_state") != "ORDINARY_COACHING":
        errors.append("initial_state must be ORDINARY_COACHING")

    states = data.get("states")
    if not isinstance(states, dict):
        return errors + ["states must be an object"]
    if set(states) != REQUIRED_STATES:
        errors.append("states must exactly declare the five governed states")
    for name, controls in states.items():
        if not isinstance(controls, dict):
            errors.append(f"state {name} controls must be an object")
            continue
        for field in ("coaching_allowed", "memory_write_allowed"):
            if not isinstance(controls.get(field), bool):
                errors.append(f"state {name} {field} must be boolean")
        if not isinstance(controls.get("resource_requirement"), str):
            errors.append(f"state {name} resource_requirement is required")
        if name in RESTRICTED_STATES and controls.get("memory_write_allowed") is not False:
            errors.append(f"restricted state {name} must freeze memory writes")
        if name in RESTRICTED_STATES and controls.get("coaching_allowed") is not False:
            errors.append(f"restricted state {name} must stop ordinary coaching")
        expected_controls = EXPECTED_STATE_CONTROLS.get(name)
        if expected_controls and (
            controls.get("coaching_allowed"),
            controls.get("memory_write_allowed"),
            controls.get("resource_requirement"),
        ) != expected_controls:
            errors.append(f"state {name} controls differ from the governed tuple")
    ordinary = states.get("ORDINARY_COACHING", {})
    if ordinary.get("coaching_allowed") is not True:
        errors.append("ORDINARY_COACHING must allow ordinary coaching")
    if ordinary.get("memory_write_allowed") is not True:
        errors.append("ORDINARY_COACHING must allow the separate consent layer to decide memory")
    acute = states.get("ACUTE_DANGER", {})
    if acute.get("resource_requirement") != "CURRENT_OR_FALLBACK":
        errors.append("ACUTE_DANGER must require current resources or fallback")

    transitions = data.get("transitions")
    if not isinstance(transitions, list):
        return errors + ["transitions must be an array"]
    rule_ids: set[str] = set()
    keys: set[tuple[str, str]] = set()
    events: set[str] = set()
    graph: dict[str, set[str]] = {state: set() for state in REQUIRED_STATES}
    for index, transition in enumerate(transitions):
        path = f"transitions[{index}]"
        if not isinstance(transition, dict):
            errors.append(f"{path} must be an object")
            continue
        rule_id = transition.get("id")
        source = transition.get("from")
        event = transition.get("event")
        target = transition.get("to")
        if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
            errors.append(f"{path}.id must match SAFE-TRANS-NNN")
        elif rule_id in rule_ids:
            errors.append(f"duplicate transition id {rule_id}")
        else:
            rule_ids.add(rule_id)
        if source not in REQUIRED_STATES or target not in REQUIRED_STATES:
            errors.append(f"{path} has unknown state")
        else:
            graph[source].add(target)
        if not isinstance(event, str) or not event:
            errors.append(f"{path}.event is required")
        else:
            events.add(event)
            key = (source, event)
            if key in keys:
                errors.append(f"duplicate transition for {source}/{event}")
            keys.add(key)
        effects = transition.get("effects", [])
        requires = transition.get("requires", [])
        if not isinstance(effects, list) or not set(effects).issubset(ALLOWED_EFFECTS):
            errors.append(f"{path}.effects contains an unsupported effect")
        if not isinstance(requires, list) or not set(requires).issubset(ALLOWED_REQUIREMENTS):
            errors.append(f"{path}.requires contains an unsupported guard")

    observed_transitions = {
        (item.get("from"), item.get("event")): (
            item.get("id"),
            item.get("to"),
            tuple(sorted(item.get("requires", []))),
            tuple(sorted(item.get("effects", []))),
        )
        for item in transitions
        if isinstance(item, dict)
    }
    expected_transitions = {
        key: (rule_id, target, tuple(sorted(requires)), tuple(sorted(effects)))
        for key, (rule_id, target, requires, effects) in EXPECTED_TRANSITIONS.items()
    }
    if observed_transitions != expected_transitions or len(transitions) != len(EXPECTED_TRANSITIONS):
        missing = sorted(set(expected_transitions) - set(observed_transitions))
        extra = sorted(set(observed_transitions) - set(expected_transitions))
        mismatched = sorted(
            key
            for key in set(expected_transitions) & set(observed_transitions)
            if expected_transitions[key] != observed_transitions[key]
        )
        errors.append(
            f"transition table differs from governed contract; missing={missing}, extra={extra}, mismatched={mismatched}"
        )

    if missing := sorted(REQUIRED_EVENTS - events):
        errors.append(f"missing required transition events: {missing}")
    reduced = next(
        (
            transition
            for transition in transitions
            if isinstance(transition, dict)
            and transition.get("from") == "ACUTE_DANGER"
            and transition.get("event") == "IMMEDIATE_DANGER_REDUCED"
        ),
        {},
    )
    if "support_connected" not in reduced.get("requires", []):
        errors.append("acute danger may reduce only after immediate support is connected")
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        effects = set(transition.get("effects", []))
        source = transition.get("from")
        target = transition.get("to")
        event = transition.get("event")
        if target == "ACUTE_DANGER" and source != "ACUTE_DANGER":
            if "freeze_memory" not in effects or "clear_support" not in effects:
                errors.append(
                    f"acute entry {source}/{event} must freeze memory and clear prior support"
                )
        if "thaw_memory" in effects and not (
            source == "ORDINARY_COACHING"
            and target == "ORDINARY_COACHING"
            and event == "MEMORY_REENABLE_CONFIRMED"
            and "memory_latched" in transition.get("requires", [])
        ):
            errors.append("only guarded MEMORY_REENABLE_CONFIRMED may thaw memory")
        if event == "SAFE_RETURN_CONFIRMED" and "thaw_memory" in effects:
            errors.append("post-crisis safe return must not thaw memory")
        if "mark_support_connected" in effects and not (
            source == "ACUTE_DANGER"
            and target == "ACUTE_DANGER"
            and event == "IMMEDIATE_SUPPORT_CONNECTED"
        ):
            errors.append("only IMMEDIATE_SUPPORT_CONNECTED may mark support connected")
        if event == "IMMEDIATE_SUPPORT_CONNECTED" and "mark_support_connected" not in effects:
            errors.append("IMMEDIATE_SUPPORT_CONNECTED must mark support connected")
        if "clear_support" in effects and not (
            target == "ACUTE_DANGER" and source != "ACUTE_DANGER"
        ):
            errors.append("only entry into ACUTE_DANGER may clear prior support")

    reachable = {"ORDINARY_COACHING"}
    frontier = ["ORDINARY_COACHING"]
    while frontier:
        source = frontier.pop()
        for target in graph.get(source, set()):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    if reachable != REQUIRED_STATES:
        errors.append(f"unreachable states: {sorted(REQUIRED_STATES - reachable)}")
    return errors


@dataclass(frozen=True)
class SafetyTransition:
    audit_event_id: str
    rule_id: str
    event: str
    state_before: SafetyState
    state_after: SafetyState
    memory_write_allowed: bool
    memory_latched: bool
    support_connected: bool
    occurred_at: str


class SafetySession:
    """Deterministic session state with fail-closed transitions and audit data."""

    def __init__(self, *, machine: dict | None = None, clock: Clock | None = None):
        candidate = deepcopy(machine) if machine is not None else load_machine()
        errors = validate_machine_spec(candidate)
        if errors:
            raise SafetyRuntimeError("invalid safety state machine: " + "; ".join(errors))
        self._machine = candidate
        self._clock = clock or _system_clock
        self._state: SafetyState = self._machine["initial_state"]
        self._memory_latched = False
        self._support_connected = False
        self._history: list[SafetyTransition] = []
        self._transitions = {
            (item["from"], item["event"]): item
            for item in self._machine["transitions"]
        }

    @property
    def state(self) -> SafetyState:
        return self._state

    @property
    def memory_latched(self) -> bool:
        return self._memory_latched

    @property
    def support_connected(self) -> bool:
        return self._support_connected

    @property
    def history(self) -> tuple[SafetyTransition, ...]:
        return tuple(self._history)

    @property
    def coaching_allowed(self) -> bool:
        return bool(self._machine["states"][self._state]["coaching_allowed"])

    @property
    def memory_write_allowed(self) -> bool:
        state_allows = self._machine["states"][self._state]["memory_write_allowed"]
        return bool(state_allows and not self._memory_latched)

    @property
    def resource_requirement(self) -> str:
        return self._machine["states"][self._state]["resource_requirement"]

    def require_memory_write_allowed(self) -> None:
        if not self.memory_write_allowed:
            raise RestrictedMemoryWrite(
                f"memory write prohibited in {self._state}; latch={self._memory_latched}"
            )

    def transition(self, event: str) -> SafetyTransition:
        rule = self._transitions.get((self._state, event))
        if rule is None:
            raise InvalidTransition(f"event {event} is invalid from {self._state}")
        requirements = set(rule.get("requires", []))
        if "support_connected" in requirements and not self._support_connected:
            raise SafetyGuardFailed("immediate support connection is not confirmed")
        if "memory_latched" in requirements and not self._memory_latched:
            raise SafetyGuardFailed("memory is not latched")

        occurred_at = _timestamp(self._clock())
        audit_event_id = "safe-event-" + secrets.token_hex(16)
        state_before = self._state
        state_after = rule["to"]
        memory_latched = self._memory_latched
        support_connected = self._support_connected
        effects = set(rule.get("effects", []))
        if "freeze_memory" in effects:
            memory_latched = True
        if "thaw_memory" in effects:
            memory_latched = False
        if "mark_support_connected" in effects:
            support_connected = True
        if "clear_support" in effects:
            support_connected = False
        memory_write_allowed = bool(
            self._machine["states"][state_after]["memory_write_allowed"]
            and not memory_latched
        )
        transition = SafetyTransition(
            audit_event_id=audit_event_id,
            rule_id=rule["id"],
            event=event,
            state_before=state_before,
            state_after=state_after,
            memory_write_allowed=memory_write_allowed,
            memory_latched=memory_latched,
            support_connected=support_connected,
            occurred_at=occurred_at,
        )
        self._history.append(transition)
        self._state = state_after
        self._memory_latched = memory_latched
        self._support_connected = support_connected
        return transition


@dataclass(frozen=True)
class ResourceRequest:
    location: str
    language: str
    requested_at: str
    urgency: Literal["ACUTE_DANGER"] = "ACUTE_DANGER"


@dataclass(frozen=True)
class VerifiedResource:
    name: str
    channel: Literal["phone", "text", "chat", "walk_in", "emergency_services"]
    contact: str
    jurisdiction: str
    source_uri: str
    verified_at: str
    expires_at: str


class TrustedResourceResolver(Protocol):
    """Host trust boundary; implementations must use current authoritative data."""

    def resolve(self, request: ResourceRequest) -> Sequence[VerifiedResource]: ...


@dataclass(frozen=True)
class ResolutionOutcome:
    status: ResolutionStatus
    resources: tuple[VerifiedResource, ...]
    fallback_actions: tuple[str, ...]
    resolver_attempted: bool
    failure_code: str | None
    resolved_at: str


_FALLBACK_ACTIONS = (
    "Contact local emergency services or a current local crisis service now.",
    "Ask a trusted person who can be physically present to stay with you.",
    "Move away from immediate means of harm when you can do so safely.",
)


def _valid_resource(
    resource: VerifiedResource, now: datetime, expected_jurisdiction: str
) -> bool:
    try:
        verified = _as_utc(datetime.fromisoformat(resource.verified_at.replace("Z", "+00:00")))
        expires = _as_utc(datetime.fromisoformat(resource.expires_at.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return False
    return all(
        (
            bool(resource.name.strip()),
            bool(resource.contact.strip()),
            bool(resource.jurisdiction.strip()),
            resource.channel in _RESOURCE_CHANNELS,
            resource.jurisdiction.strip().casefold()
            == expected_jurisdiction.strip().casefold(),
            bool(_HTTPS_URI.fullmatch(resource.source_uri)),
            verified <= now < expires,
        )
    )


def resolve_current_resources(
    session: SafetySession,
    resolver: TrustedResourceResolver,
    *,
    location: str | None,
    language: str,
    clock: Clock | None = None,
) -> ResolutionOutcome:
    """Resolve current resources or return a content-free fail-safe fallback."""

    if session.state != "ACUTE_DANGER":
        raise ResourceResolutionError("current-resource lookup requires ACUTE_DANGER")
    now = _as_utc((clock or _system_clock)())
    if location is None or not location.strip():
        return ResolutionOutcome(
            status="LOCATION_REQUIRED",
            resources=(),
            fallback_actions=_FALLBACK_ACTIONS,
            resolver_attempted=False,
            failure_code="LOCATION_NOT_AVAILABLE",
            resolved_at=_timestamp(now),
        )
    request = ResourceRequest(
        location=location.strip(),
        language=language.strip() or "und",
        requested_at=_timestamp(now),
    )
    try:
        resources = tuple(resolver.resolve(request))
    except Exception:
        resources = ()
        failure_code = "HOST_RESOLVER_FAILED"
    else:
        failure_code = None
    try:
        valid_resources = bool(resources) and all(
            isinstance(resource, VerifiedResource)
            and _valid_resource(resource, now, request.location)
            for resource in resources
        )
    except (AttributeError, TypeError, ValueError):
        valid_resources = False
    if not valid_resources:
        return ResolutionOutcome(
            status="UNAVAILABLE",
            resources=(),
            fallback_actions=_FALLBACK_ACTIONS,
            resolver_attempted=True,
            failure_code=failure_code or "INVALID_OR_STALE_HOST_RESULT",
            resolved_at=_timestamp(now),
        )
    return ResolutionOutcome(
        status="VERIFIED",
        resources=resources,
        fallback_actions=_FALLBACK_ACTIONS,
        resolver_attempted=True,
        failure_code=None,
        resolved_at=_timestamp(now),
    )


def resource_claims_are_verified(
    outcome: ResolutionOutcome, claims: Sequence[dict[str, str]]
) -> bool:
    """Require every rendered contact claim to match the verified host result."""

    allowed = {
        (resource.name, resource.contact, resource.source_uri)
        for resource in outcome.resources
    }
    normalized = {
        (claim.get("name", ""), claim.get("contact", ""), claim.get("source_uri", ""))
        for claim in claims
    }
    return normalized.issubset(allowed)
