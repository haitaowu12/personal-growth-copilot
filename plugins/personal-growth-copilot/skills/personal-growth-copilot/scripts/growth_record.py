#!/usr/bin/env python3
"""Create, validate, and summarize portable Personal Growth Copilot records.

The Draft 2020-12 JSON Schema is the structural authority. This module adds
cross-record semantic checks that JSON Schema cannot express, including unique
IDs, referential integrity, and prohibited raw/sensitive field names.

This utility never modifies an existing record. Use ``record_store.py`` for
host-neutral preview, consent, atomic commit, correction, export, and deletion
semantics. A persistent host still needs a separate privacy preflight.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

POLICIES = {"OFF", "SESSION_ONLY", "CONFIRM_EACH"}
COLLECTIONS = (
    "preferences",
    "evidence",
    "goals",
    "hypotheses",
    "experiments",
    "scales",
    "check_ins",
    "decisions",
    "learning",
    "corrections",
)
PROHIBITED_KEYS = {
    "raw_transcript",
    "raw_journal",
    "trauma_narrative",
    "credential",
    "credentials",
    "password",
    "intimate_media",
    "third_party_profile",
    "hidden_reasoning",
}
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "assets/growth-record.schema.json"
EVIDENCE_SOURCE_PATH = (
    Path(__file__).resolve().parents[1] / "assets/evidence-source-ids.json"
)


@lru_cache(maxsize=1)
def schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_error(error: Any) -> str:
    return (
        f"{error.json_path}: value violates the {error.validator} constraint "
        f"[schema:{error.validator}]"
    )


def validate_against_schema(data: Any) -> list[str]:
    errors = sorted(
        schema_validator().iter_errors(data),
        key=lambda item: (
            tuple(str(part) for part in item.absolute_path),
            str(item.validator),
            item.message,
        ),
    )
    return [_schema_error(error) for error in errors]


def _walk_keys(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in PROHIBITED_KEYS:
                errors.append(f"{path}.{key}: prohibited sensitive/raw field")
            errors.extend(_walk_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_keys(child, f"{path}[{index}]"))
    return errors


def _walk_nonfinite(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            errors.extend(_walk_nonfinite(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_nonfinite(child, f"{path}[{index}]"))
    elif isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{path}: non-finite numbers are prohibited")
    return errors


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def evidence_source_ids() -> frozenset[str]:
    manifest = json.loads(EVIDENCE_SOURCE_PATH.read_text(encoding="utf-8"))
    return frozenset(source["id"] for source in manifest["sources"])


def temporal_status(item: dict[str, Any], at: datetime) -> str:
    """Classify a material dossier item without inventing a universal TTL."""

    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("temporal inventory timestamp requires a timezone")
    moment = at.astimezone(timezone.utc)
    if item.get("status") in {"superseded", "rejected", "retired"} or item.get(
        "superseded"
    ) is True:
        return "INACTIVE"
    start_value = next(
        (
            item[field]
            for field in (
                "last_confirmed_at",
                "confirmed_at",
                "updated_at",
                "captured_at",
                "start_at",
                "created_at",
            )
            if item.get(field)
        ),
        None,
    )
    if start_value is not None and moment < _parse_timestamp(start_value):
        return "FUTURE_INVALID"
    review_at = item.get("review_at")
    if review_at is not None and moment >= _parse_timestamp(review_at):
        return "REVIEW_DUE"
    return "CURRENT"


def temporal_inventory(data: dict[str, Any], at: datetime) -> list[dict[str, str]]:
    if validate_record(data):
        raise ValueError("temporal inventory requires a valid growth record")
    result: list[dict[str, str]] = []
    for collection in (
        "preferences",
        "evidence",
        "goals",
        "hypotheses",
        "experiments",
        "scales",
        "decisions",
    ):
        for item in data.get(collection, []):
            result.append(
                {
                    "collection": collection,
                    "id": item["id"],
                    "status": temporal_status(item, at),
                }
            )
    return result


def validate_record(data: Any) -> list[str]:
    """Return canonical-schema and semantic-integrity errors for ``data``."""

    schema_errors = validate_against_schema(data)
    errors = list(schema_errors)
    errors.extend(_walk_keys(data))
    nonfinite_errors = _walk_nonfinite(data)
    errors.extend(nonfinite_errors)
    if schema_errors or nonfinite_errors:
        return sorted(set(errors))
    if not isinstance(data, dict):
        return errors

    seen_ids: set[str] = set()
    hypothesis_ids: set[str] = set()
    experiment_ids: set[str] = set()
    evidence_ids: set[str] = set()
    scales: dict[str, dict[str, Any]] = {}
    scale_indexes: dict[str, int] = {}
    decision_ids: set[str] = set()
    correction_rows: list[tuple[int, dict[str, Any]]] = []

    for collection in COLLECTIONS:
        items = data.get(collection, [])
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                continue
            if item_id in seen_ids:
                errors.append(f"$.{collection}[{index}].id: duplicate id")
                continue
            seen_ids.add(item_id)
            if collection == "hypotheses":
                hypothesis_ids.add(item_id)
            elif collection == "experiments":
                experiment_ids.add(item_id)
            elif collection == "evidence":
                evidence_ids.add(item_id)
            elif collection == "scales":
                scales[item_id] = item
                scale_indexes[item_id] = index
            elif collection == "decisions":
                decision_ids.add(item_id)
            elif collection == "corrections":
                correction_rows.append((index, item))

    temporal_fields = {
        "preferences": ("confirmed_at", "review_at"),
        "evidence": ("captured_at", "review_at"),
        "hypotheses": ("updated_at", "review_at"),
        "experiments": ("start_at", "review_at"),
        "scales": ("created_at", "review_at"),
        "decisions": ("created_at", "review_at"),
    }
    for collection, (start_field, review_field) in temporal_fields.items():
        items = data.get(collection, [])
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get(review_field):
                continue
            try:
                start = _parse_timestamp(item[start_field])
                review = _parse_timestamp(item[review_field])
            except (KeyError, TypeError, ValueError):
                continue
            if review <= start:
                errors.append(
                    f"$.{collection}[{index}].{review_field}: must be after {start_field}"
                )

    evidence_items = data.get("evidence", [])
    if not isinstance(evidence_items, list):
        evidence_items = []
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            continue
        last_confirmed = item.get("last_confirmed_at")
        if last_confirmed:
            try:
                confirmed = _parse_timestamp(last_confirmed)
                if confirmed < _parse_timestamp(item["captured_at"]):
                    errors.append(
                        f"$.evidence[{index}].last_confirmed_at: precedes captured_at"
                    )
                if item.get("review_at") and _parse_timestamp(item["review_at"]) <= confirmed:
                    errors.append(
                        f"$.evidence[{index}].review_at: must be after last_confirmed_at"
                    )
            except (KeyError, TypeError, ValueError):
                pass
        origin_kind = item.get("origin_kind")
        source = item.get("source")
        citation = item.get("source_citation_id")
        if origin_kind == "EXTERNAL_SOURCE":
            if isinstance(citation, str) and citation not in evidence_source_ids():
                errors.append(
                    f"$.evidence[{index}].source_citation_id: unknown evidence source"
                )
        elif citation is not None:
            errors.append(
                f"$.evidence[{index}].source_citation_id: only external evidence may cite the research ledger"
            )
        if origin_kind == "USER_STATEMENT" and source != "USER-REPORTED":
            errors.append(
                f"$.evidence[{index}].source: USER_STATEMENT must be USER-REPORTED"
            )
        if origin_kind == "CORRECTION" and source != "CORRECTION":
            errors.append(
                f"$.evidence[{index}].source: CORRECTION origin must use CORRECTION provenance"
            )

    hypotheses = data.get("hypotheses", [])
    if isinstance(hypotheses, list):
        for index, item in enumerate(hypotheses):
            if not isinstance(item, dict):
                continue
            for field in (
                "supporting_evidence_ids",
                "disconfirming_or_missing_evidence_ids",
            ):
                for evidence_id in item.get(field, []):
                    if isinstance(evidence_id, str) and evidence_id not in evidence_ids:
                        errors.append(
                            f"$.hypotheses[{index}].{field}: unknown evidence"
                        )
            for alternative_id in item.get("alternative_hypothesis_ids", []):
                if not isinstance(alternative_id, str):
                    continue
                if alternative_id == item.get("id"):
                    errors.append(
                        f"$.hypotheses[{index}].alternative_hypothesis_ids: hypothesis cannot reference itself"
                    )
                elif alternative_id not in hypothesis_ids:
                    errors.append(
                        f"$.hypotheses[{index}].alternative_hypothesis_ids: unknown hypothesis"
                    )

    experiments = data.get("experiments", [])
    if isinstance(experiments, list):
        for index, item in enumerate(experiments):
            if not isinstance(item, dict):
                continue
            hypothesis_id = item.get("hypothesis_id")
            if isinstance(hypothesis_id, str) and hypothesis_id not in hypothesis_ids:
                errors.append(
                    f"$.experiments[{index}].hypothesis_id: unknown hypothesis"
                )
            if item.get("status") == "active" and not item.get("review_at"):
                errors.append(
                    f"$.experiments[{index}].review_at: active experiment requires a review date"
                )
            if item.get("status") == "active" and not item.get("start_at"):
                errors.append(
                    f"$.experiments[{index}].start_at: active experiment requires a start date"
                )

    goals = data.get("goals", [])
    if isinstance(goals, list):
        for index, item in enumerate(goals):
            if (
                isinstance(item, dict)
                and item.get("status") == "active"
                and not item.get("review_at")
            ):
                errors.append(
                    f"$.goals[{index}].review_at: active goal requires a review date"
                )

    learning = data.get("learning", [])
    if isinstance(learning, list):
        for index, item in enumerate(learning):
            if not isinstance(item, dict):
                continue
            experiment_id = item.get("experiment_id")
            if isinstance(experiment_id, str) and experiment_id not in experiment_ids:
                errors.append(
                    f"$.learning[{index}].experiment_id: unknown experiment"
                )

    check_ins = data.get("check_ins", [])
    if isinstance(check_ins, list):
        for index, item in enumerate(check_ins):
            if not isinstance(item, dict):
                continue
            scale_id = item.get("scale_id")
            scale = scales.get(scale_id) if isinstance(scale_id, str) else None
            if scale is None:
                errors.append(f"$.check_ins[{index}].scale_id: unknown scale")
                continue
            minimum = scale.get("minimum")
            maximum = scale.get("maximum")
            value = item.get("value")
            if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
                if minimum >= maximum:
                    errors.append(
                        f"$.scales[{scale_indexes[scale_id]}]: minimum must be below maximum"
                    )
                if isinstance(value, (int, float)) and not minimum <= value <= maximum:
                    errors.append(
                        f"$.check_ins[{index}].value: outside scale bounds"
                    )
            try:
                if _parse_timestamp(item["recorded_at"]) < _parse_timestamp(scale["created_at"]):
                    errors.append(
                        f"$.check_ins[{index}].recorded_at: precedes scale creation"
                    )
                if _parse_timestamp(item["recorded_at"]) >= _parse_timestamp(scale["review_at"]):
                    errors.append(
                        f"$.check_ins[{index}].recorded_at: scale review is due"
                    )
            except (KeyError, TypeError, ValueError):
                pass

    decisions = data.get("decisions", [])
    if isinstance(decisions, list):
        for index, item in enumerate(decisions):
            if not isinstance(item, dict):
                continue
            option_ids = [
                option.get("id")
                for option in item.get("options", [])
                if isinstance(option, dict) and isinstance(option.get("id"), str)
            ]
            if len(option_ids) != len(set(option_ids)):
                errors.append(f"$.decisions[{index}].options: duplicate option id")
            option_set = set(option_ids)
            for field in ("recommended_option_id", "selected_option_id"):
                option_id = item.get(field)
                if isinstance(option_id, str) and option_id not in option_set:
                    errors.append(
                        f"$.decisions[{index}].{field}: unknown option"
                    )
            if item.get("status") == "chosen":
                if not item.get("selected_option_id") or item.get("chosen_by") != "USER":
                    errors.append(
                        f"$.decisions[{index}]: chosen decisions require a user-selected option"
                    )
            elif item.get("selected_option_id") or item.get("chosen_by"):
                errors.append(
                    f"$.decisions[{index}]: only chosen decisions may record a selection"
                )
            if item.get("status") in {"open", "chosen", "deferred"} and not item.get(
                "review_at"
            ):
                errors.append(
                    f"$.decisions[{index}].review_at: live decision requires a review date"
                )
            for evidence_id in item.get("evidence_ids", []):
                if isinstance(evidence_id, str) and evidence_id not in evidence_ids:
                    errors.append(
                        f"$.decisions[{index}].evidence_ids: unknown evidence"
                    )
            supersedes = item.get("supersedes_decision_id")
            if supersedes == item.get("id"):
                errors.append(
                    f"$.decisions[{index}].supersedes_decision_id: decision cannot supersede itself"
                )
            elif isinstance(supersedes, str) and supersedes not in decision_ids:
                errors.append(
                    f"$.decisions[{index}].supersedes_decision_id: unknown decision"
                )

        supersedes_by_id = {
            item["id"]: (
                item.get("supersedes_decision_id")
                if isinstance(item.get("supersedes_decision_id"), str)
                else None
            )
            for item in decisions
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for decision_id in supersedes_by_id:
            path: set[str] = set()
            current: str | None = decision_id
            while current is not None and current in supersedes_by_id:
                if current in path:
                    errors.append(
                        "$.decisions: supersession cycle"
                    )
                    break
                path.add(current)
                current = supersedes_by_id[current]

    for index, correction in correction_rows:
        target_id = correction.get("target_id")
        correction_id = correction.get("id")
        if target_id == correction_id:
            errors.append(
                f"$.corrections[{index}].target_id: correction cannot target itself"
            )
        elif isinstance(target_id, str) and target_id not in seen_ids:
            errors.append(
                f"$.corrections[{index}].target_id: unknown target"
            )

    return sorted(set(errors))


def empty_record(record_id: str, purpose: str, policy: str) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "record_id": record_id,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": purpose,
        "memory_policy": policy,
        "boundaries": [],
        "preferences": [],
        "evidence": [],
        "goals": [],
        "hypotheses": [],
        "experiments": [],
        "scales": [],
        "check_ins": [],
        "decisions": [],
        "learning": [],
        "corrections": [],
    }


def load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard numeric constant is prohibited: {value}")
        ),
    )


def command_validate(path: Path) -> int:
    errors = validate_record(load(path))
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


def command_init(path: Path, record_id: str, purpose: str, policy: str) -> int:
    if path.exists():
        print(f"refusing to overwrite existing record: {path}", file=sys.stderr)
        return 2
    data = empty_record(record_id, purpose, policy)
    errors = validate_record(data)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, indent=2), file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"created new empty record: {path}")
    print("No future write is implied; preview and confirm each material change.")
    return 0


def command_summary(path: Path) -> int:
    data = load(path)
    errors = validate_record(data)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "record_id": data["record_id"],
                "updated_at": data["updated_at"],
                "memory_policy": data["memory_policy"],
                "counts": {name: len(data.get(name, [])) for name in COLLECTIONS},
            },
            indent=2,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("path", type=Path)

    init = sub.add_parser("init")
    init.add_argument("path", type=Path)
    init.add_argument("--record-id", required=True)
    init.add_argument("--purpose", default="")
    init.add_argument("--policy", choices=sorted(POLICIES), default="CONFIRM_EACH")

    summary = sub.add_parser("summary")
    summary.add_argument("path", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "validate":
        return command_validate(args.path)
    if args.command == "init":
        return command_init(args.path, args.record_id, args.purpose, args.policy)
    if args.command == "summary":
        return command_summary(args.path)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
