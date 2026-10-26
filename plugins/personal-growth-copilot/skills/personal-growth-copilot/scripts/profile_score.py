#!/usr/bin/env python3
"""Calculate an inspectable Decision Fit Score from an explicit JSON model.

This utility performs arithmetic and structural validation only. It does not
infer dimensions, evidence, weights, ratings, confidence, consent, safety, or
relationship outcomes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.1"
SUPPORTED_INPUT_SCHEMAS = {"1.0", "1.1"}
CONFIDENCE_VALUES = {"low", "moderate", "high"}
FLAG_TYPES = {"deal_breaker", "safety", "authority", "privacy"}
FLAG_STATUSES = {"active", "resolved"}
MODES = {"session-only", "persistent"}


def require_text(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")


def require_iso_date(value: Any, field: str, errors: list[str]) -> None:
    require_text(value, field, errors)
    if isinstance(value, str):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("date format")
            dt.date.fromisoformat(value)
        except ValueError:
            errors.append(f"{field} must use YYYY-MM-DD")


def validate_evidence_items(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return
    for index, item in enumerate(value):
        prefix = f"{field}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require_text(item.get("summary"), f"{prefix}.summary", errors)
        require_text(item.get("source"), f"{prefix}.source", errors)
        require_iso_date(item.get("date"), f"{prefix}.date", errors)


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["input must be an object"]
    if not isinstance(payload.get("schema_version"), str) or payload["schema_version"] not in SUPPORTED_INPUT_SCHEMAS:
        errors.append("schema_version must be 1.0 or 1.1")
    require_text(payload.get("profile_id"), "profile_id", errors)
    require_text(payload.get("purpose"), "purpose", errors)
    require_iso_date(payload.get("as_of"), "as_of", errors)
    require_text(payload.get("review_or_expiry"), "review_or_expiry", errors)
    if not isinstance(payload.get("mode"), str) or payload["mode"] not in MODES:
        errors.append("mode must be session-only or persistent")
    exclusions = payload.get("sensitive_exclusions")
    if not isinstance(exclusions, list) or not all(
        isinstance(item, str) and item.strip() for item in exclusions
    ):
        errors.append("sensitive_exclusions must be a list of non-empty strings")
    version = payload.get("profile_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("profile_version must be an integer >= 1")

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return errors + ["dimensions must be a non-empty list"]

    ids: set[str] = set()
    positive_weight = False
    for index, dimension in enumerate(dimensions):
        prefix = f"dimensions[{index}]"
        if not isinstance(dimension, dict):
            errors.append(f"{prefix} must be an object")
            continue
        dimension_id = dimension.get("id")
        require_text(dimension_id, f"{prefix}.id", errors)
        if isinstance(dimension_id, str):
            if dimension_id in ids:
                errors.append(f"duplicate dimension id: {dimension_id}")
            ids.add(dimension_id)
        require_text(dimension.get("label"), f"{prefix}.label", errors)
        require_text(dimension.get("anchor"), f"{prefix}.anchor", errors)
        require_text(dimension.get("materiality"), f"{prefix}.materiality", errors)

        weight = dimension.get("weight")
        if (
            not isinstance(weight, int)
            or isinstance(weight, bool)
            or not 0 <= weight <= 3
        ):
            errors.append(f"{prefix}.weight must be an integer from 0 to 3")
        elif weight > 0:
            positive_weight = True

        critical = dimension.get("decision_critical", True)
        if not isinstance(critical, bool):
            errors.append(f"{prefix}.decision_critical must be boolean")

        rating = dimension.get("rating")
        if rating is not None and (
            not isinstance(rating, int)
            or isinstance(rating, bool)
            or not 0 <= rating <= 5
        ):
            errors.append(f"{prefix}.rating must be null or an integer from 0 to 5")

        confidence = dimension.get("confidence")
        if rating is None:
            if confidence not in (None, "unknown"):
                errors.append(
                    f"{prefix}.confidence must be null or unknown when rating is null"
                )
        elif not isinstance(confidence, str) or confidence not in CONFIDENCE_VALUES:
            errors.append(f"{prefix}.confidence must be low, moderate, or high")

        validate_evidence_items(
            dimension.get("evidence"), f"{prefix}.evidence", errors
        )
        validate_evidence_items(
            dimension.get("counterevidence"), f"{prefix}.counterevidence", errors
        )
        unknowns = dimension.get("unknowns")
        if not isinstance(unknowns, list) or not all(
            isinstance(item, str) and item.strip() for item in unknowns
        ):
            errors.append(f"{prefix}.unknowns must be a list of non-empty strings")
        if (
            rating is not None
            and isinstance(weight, int)
            and not isinstance(weight, bool)
            and weight > 0
            and isinstance(dimension.get("evidence"), list)
            and not dimension["evidence"]
        ):
            errors.append(f"{prefix}.evidence requires at least one sourced item when rated")
        require_text(
            dimension.get("update_condition"),
            f"{prefix}.update_condition",
            errors,
        )

    if not positive_weight:
        errors.append("at least one dimension must have positive weight")

    flags = payload.get("flags", [])
    if not isinstance(flags, list):
        errors.append("flags must be a list")
    else:
        for index, flag in enumerate(flags):
            prefix = f"flags[{index}]"
            if not isinstance(flag, dict):
                errors.append(f"{prefix} must be an object")
                continue
            if not isinstance(flag.get("type"), str) or flag["type"] not in FLAG_TYPES:
                errors.append(
                    f"{prefix}.type must be one of {', '.join(sorted(FLAG_TYPES))}"
                )
            if not isinstance(flag.get("status"), str) or flag["status"] not in FLAG_STATUSES:
                errors.append(f"{prefix}.status must be active or resolved")
            require_text(flag.get("description"), f"{prefix}.description", errors)

    return errors


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_payload(payload)
    if errors:
        raise ValueError("; ".join(errors))

    dimensions = payload["dimensions"]
    weighted = [item for item in dimensions if item["weight"] > 0]
    planned_weight = sum(item["weight"] for item in weighted)
    scored = [item for item in weighted if item["rating"] is not None]
    missing = [item for item in weighted if item["rating"] is None]
    scored_weight = sum(item["weight"] for item in scored)
    observed_sum = sum(item["weight"] * item["rating"] for item in scored)
    partial_score = round(20 * observed_sum / scored_weight, 2) if scored_weight else None
    critical_unknowns = [
        item["id"] for item in weighted
        if item.get("decision_critical", True)
        and (item["rating"] is None or item["unknowns"])
    ]
    active_flags = [flag for flag in payload.get("flags", []) if flag["status"] == "active"]
    # Presentation gates precede arithmetic. Defaults are conservative for v1.0 input.
    if active_flags:
        status, headline = "gated", "Blocked: resolve the active flag through the appropriate route."
    elif not scored:
        status, headline = "not_calculable", "No rated evidence; an overall score is not calculable."
    elif critical_unknowns:
        status, headline = "insufficient_evidence", "Decision-critical information is unresolved; no overall assessment."
    elif missing:
        status, headline = "partial", "Partial arithmetic only; no overall assessment."
    else:
        status, headline = "scored", "Complete arithmetic under the user's model; not a prediction or recommendation."

    return {
        "schema_version": SCHEMA_VERSION,
        "input_schema_version": payload["schema_version"],
        "profile_id": payload["profile_id"],
        "profile_version": payload["profile_version"],
        "purpose": payload["purpose"],
        "as_of": payload["as_of"],
        "review_or_expiry": payload["review_or_expiry"],
        "mode": payload["mode"],
        "decision_status": status,
        "decision_fit_score": partial_score if status == "scored" else None,
        "interpretation": headline,
        "coverage_percent": round(100 * scored_weight / planned_weight, 2),
        "planned_weight": planned_weight,
        "scored_weight": scored_weight,
        "unscored_dimensions": [item["id"] for item in missing],
        "decision_critical_unknowns": critical_unknowns,
        "dimension_confidence": {item["id"]: item["confidence"] for item in scored},
        "active_flags": active_flags,
        "arithmetic_only": {
            "scored_dimensions_score": partial_score,
            "full_model_bounds": [
                round(20 * observed_sum / planned_weight, 2),
                round(20 * (observed_sum + 5 * (planned_weight - scored_weight)) / planned_weight, 2),
            ],
            "bounds_meaning": "Unknown ratings span 0 to 5. Sensitivity bounds, not a confidence interval; flags still govern.",
        },
        "nonclaim": (
            "Custom decision aid only; not human worth, diagnosis, consent, "
            "deception detection, legal status, compatibility validation, or an outcome guarantee. "
            "Render decision_status and interpretation before arithmetic; never promote a partial or gated number."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = calculate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, indent=2))
        return 1

    rendered = json.dumps(
        {"status": "pass", "result": result},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
