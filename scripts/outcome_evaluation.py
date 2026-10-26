#!/usr/bin/env python3
"""Validate complete outcome observations and derive non-qualifying summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "evals/outcome-measures.json"
OBSERVATION_SCHEMA = ROOT / "evals/outcome-observations.schema.json"
RESULT_SCHEMA = ROOT / "evals/outcome-result.schema.json"


class OutcomeEvaluationError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OutcomeEvaluationError("outcome-analysis clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _safe_evidence(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise OutcomeEvaluationError("outcome evidence path is unsafe")
    candidate = root / path
    if candidate.is_symlink():
        raise OutcomeEvaluationError("outcome evidence path may not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise OutcomeEvaluationError(
            "outcome evidence path is unavailable or escaped its source root"
        ) from exc
    if not resolved.is_file():
        raise OutcomeEvaluationError("outcome evidence must be a regular file")
    return resolved


def _valid_value(measure: dict[str, Any], value: Any) -> bool:
    value_type = measure["value_type"]
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "count":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if value_type == "duration":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    if value_type in {"ordinal", "categorical"}:
        return isinstance(value, str) and value in measure.get("anchors", [])
    return False


def validate_observations(
    document: dict[str, Any], *, source_path: Path
) -> list[str]:
    errors = schema_errors(document, OBSERVATION_SCHEMA)
    if errors:
        return errors
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    if document["design_sha256"] != digest(design):
        errors.append("outcome observations differ from the governed measure design")
    roster = document["episode_roster"]
    episode_ids = [item["episode_id"] for item in roster]
    if len(episode_ids) != len(set(episode_ids)):
        errors.append("episode roster ids must be unique")
    roster_by_id = {item["episode_id"]: item for item in roster}
    measure_by_id = {item["id"]: item for item in design["measures"]}
    expected = {
        (episode["episode_id"], episode["system_id"], measure["id"], point)
        for episode in roster
        for measure in design["measures"]
        for point in measure["collection_points"]
    }
    observed_keys: set[tuple[str, str, str, str]] = set()
    observation_ids: set[str] = set()
    root = source_path.parent.resolve()
    for item in document["observations"]:
        if item["observation_id"] in observation_ids:
            errors.append("observation ids must be unique")
        observation_ids.add(item["observation_id"])
        episode = roster_by_id.get(item["episode_id"])
        measure = measure_by_id.get(item["measure_id"])
        key = (
            item["episode_id"],
            item["system_id"],
            item["measure_id"],
            item["collection_point"],
        )
        if key in observed_keys:
            errors.append("duplicate outcome observation key")
        observed_keys.add(key)
        if episode is None:
            errors.append("outcome observation names an unknown episode")
        elif episode["system_id"] != item["system_id"]:
            errors.append("outcome observation system differs from its episode roster")
        if measure is None:
            errors.append("outcome observation names an unknown measure")
            continue
        if item["collection_point"] not in measure["collection_points"]:
            errors.append("outcome observation uses an ungoverned collection point")
        if item["status"] == "OBSERVED":
            if not _valid_value(measure, item["value"]):
                errors.append("observed outcome value does not match its governed type or anchors")
            if (
                item["observed_at"] is None
                or item["evidence_path"] is None
                or item["evidence_sha256"] is None
            ):
                errors.append("observed outcomes require time and source evidence")
            else:
                try:
                    evidence = _safe_evidence(root, item["evidence_path"])
                    if hashlib.sha256(evidence.read_bytes()).hexdigest() != item[
                        "evidence_sha256"
                    ]:
                        errors.append("outcome evidence hash mismatch")
                except OutcomeEvaluationError as exc:
                    errors.append(str(exc))
        elif any(
            item[field] is not None
            for field in ("value", "observed_at", "evidence_path", "evidence_sha256")
        ):
            errors.append("non-observed outcomes must not carry a value or evidence")
    if observed_keys != expected:
        missing = len(expected - observed_keys)
        extra = len(observed_keys - expected)
        errors.append(
            f"outcome observations must cover the exact episode/measure schedule (missing={missing}, extra={extra})"
        )
    return errors


def _primary_success(measure_id: str, value: Any) -> bool:
    if measure_id == "user_confirmed_decision_state_improved":
        return value in {"clearer_choice", "better_specified_uncertainty"}
    if measure_id == "review_point_learning_completed":
        return value in {
            "observation_recorded_model_unchanged",
            "observation_recorded_model_updated",
        }
    return False


def analyze(
    document: dict[str, Any], *, source_path: Path, generated_at: datetime
) -> dict[str, Any]:
    if errors := validate_observations(document, source_path=source_path):
        raise OutcomeEvaluationError("; ".join(errors))
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    measure_by_id = {item["id"]: item for item in design["measures"]}
    summaries = []
    systems = [
        system
        for system in target_system_order()
        if any(item["system_id"] == system for item in document["episode_roster"])
    ]
    for measure in design["measures"]:
        for system in systems:
            for point in measure["collection_points"]:
                selected = [
                    item
                    for item in document["observations"]
                    if item["measure_id"] == measure["id"]
                    and item["system_id"] == system
                    and item["collection_point"] == point
                ]
                statuses = Counter(item["status"] for item in selected)
                observed = [item["value"] for item in selected if item["status"] == "OBSERVED"]
                value_counts = Counter(
                    json.dumps(value, sort_keys=True) for value in observed
                )
                numeric = [
                    float(value)
                    for value in observed
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                ]
                numeric_summary = (
                    {
                        "count": len(numeric),
                        "minimum": min(numeric),
                        "maximum": max(numeric),
                        "mean": sum(numeric) / len(numeric),
                    }
                    if numeric
                    else None
                )
                success_count = None
                rate_denominator = None
                success_rate = None
                if measure["role"] == "primary":
                    success_count = sum(
                        _primary_success(measure["id"], value) for value in observed
                    )
                    # Missing, declined, and observed null/adverse values remain in denominator;
                    # NOT_DUE is excluded because the review point has not happened yet.
                    rate_denominator = len(selected) - statuses.get("NOT_DUE", 0)
                    success_rate = (
                        success_count / rate_denominator
                        if rate_denominator
                        else None
                    )
                summaries.append(
                    {
                        "measure_id": measure["id"],
                        "layer": measure["layer"],
                        "role": measure["role"],
                        "system_id": system,
                        "collection_point": point,
                        "denominator": len(selected),
                        "status_counts": dict(sorted(statuses.items())),
                        "value_counts": dict(sorted(value_counts.items())),
                        "numeric_summary": numeric_summary,
                        "primary_success_count": success_count,
                        "primary_rate_denominator": rate_denominator,
                        "primary_success_rate": success_rate,
                    }
                )
    result = {
        "schema_version": "1.0",
        "evidence_class": "product-outcome-analysis",
        "qualification_claim_allowed": False,
        "candidate_commit": document["candidate_commit"],
        "design_sha256": document["design_sha256"],
        "observations_sha256": digest(document),
        "generated_at": timestamp(generated_at),
        "episode_count": len(document["episode_roster"]),
        "participant_states": dict(
            sorted(Counter(item["participant_state"] for item in document["episode_roster"]).items())
        ),
        "primary_outcome_ids": design["primary_outcome_ids"],
        "measure_summaries": summaries,
        "claim_limit": (
            "This deterministic analysis preserves observed, missing, declined, not-due, "
            "withdrawn, and dropout states. It reports distributions and fixed primary "
            "outcomes but does not establish causal efficacy, generalized benefit, or release readiness."
        ),
    }
    result["result_sha256"] = digest(result)
    if errors := schema_errors(result, RESULT_SCHEMA):
        raise OutcomeEvaluationError(
            "outcome result schema failure: " + "; ".join(errors)
        )
    return result


def target_system_order() -> tuple[str, ...]:
    sys.path.insert(0, str(ROOT / "evals"))
    import system_profiles

    return system_profiles.SYSTEM_IDS


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise OutcomeEvaluationError("outcome output is create-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--observations", type=Path, required=True)
    analyze_command = commands.add_parser("analyze")
    analyze_command.add_argument("--observations", type=Path, required=True)
    analyze_command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = json.loads(args.observations.read_text(encoding="utf-8"))
        errors = validate_observations(document, source_path=args.observations)
        if args.command == "validate":
            print(
                json.dumps(
                    {"status": "pass" if not errors else "fail", "errors": errors},
                    indent=2,
                )
            )
            return 1 if errors else 0
        if errors:
            raise OutcomeEvaluationError("; ".join(errors))
        result = analyze(
            document,
            source_path=args.observations,
            generated_at=datetime.now(timezone.utc),
        )
        write_new(args.output, result)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "output": str(args.output),
                    "result_sha256": result["result_sha256"],
                    "qualification_claim_allowed": False,
                },
                indent=2,
            )
        )
        return 0
    except (json.JSONDecodeError, OSError, OutcomeEvaluationError) as exc:
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
