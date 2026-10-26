#!/usr/bin/env python3
"""Validate and summarize the preregistered learning feasibility evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
TOPIC = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/learning/requirements-writing.json"
PROTOCOL = ROOT / "docs/LEARNING_PILOT.md"
CONTENT_REVIEW_SCHEMA = ROOT / "evals/learning-content-review.schema.json"
OBSERVATIONS_SCHEMA = ROOT / "evals/learning-feasibility-observations.schema.json"
RESULT_SCHEMA = ROOT / "evals/learning-feasibility-result.schema.json"


class LearningFeasibilityError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_errors(value: object, path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
            key=lambda item: list(item.absolute_path),
        )
    ]


def _safe_file(root: Path, relative: str) -> Path:
    candidate = root / relative
    if candidate.is_symlink():
        raise LearningFeasibilityError("learning evidence path may not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise LearningFeasibilityError("learning evidence path escaped its source root") from exc
    if not resolved.is_file():
        raise LearningFeasibilityError("learning evidence must be a regular file")
    return resolved


def _verify_file(root: Path, relative: str, expected: str) -> None:
    if file_hash(_safe_file(root, relative)) != expected:
        raise LearningFeasibilityError("learning evidence hash mismatch")


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LearningFeasibilityError("learning timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LearningFeasibilityError("learning timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def validate_observations(document: dict[str, Any], source_path: Path) -> list[str]:
    errors = schema_errors(document, OBSERVATIONS_SCHEMA)
    if errors:
        return errors
    root = source_path.parent.resolve()
    if document["topic_sha256"] != file_hash(TOPIC):
        errors.append("learning observations differ from the governed topic bytes")
    if document["protocol_sha256"] != file_hash(PROTOCOL):
        errors.append("learning observations differ from the governed pilot protocol")
    try:
        review_path = _safe_file(root, document["content_review_path"])
        if file_hash(review_path) != document["content_review_sha256"]:
            errors.append("learning content-review file hash mismatch")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review_errors := schema_errors(review, CONTENT_REVIEW_SCHEMA):
            errors.append("learning content review fails schema: " + "; ".join(review_errors))
        else:
            candidate = dict(review)
            expected_hash = candidate.pop("review_sha256")
            if expected_hash != digest(candidate):
                errors.append("learning content review self-hash mismatch")
            if review["candidate_commit"] != document["candidate_commit"]:
                errors.append("learning content review binds another candidate")
            if review["topic_sha256"] != document["topic_sha256"]:
                errors.append("learning content review binds another topic")
            if not all(
                review[field]
                for field in (
                    "source_accuracy_passed",
                    "answer_key_passed",
                    "rubric_alignment_passed",
                )
            ) or review["known_issues"]:
                errors.append("learning content review is not passing")
            for prefix in ("identity", "independence"):
                _verify_file(
                    root,
                    review[f"{prefix}_evidence_path"],
                    review[f"{prefix}_evidence_sha256"],
                )
    except (LearningFeasibilityError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    participant_ids: set[str] = set()
    task_ids: set[str] = set()
    reviewer_ids: set[str] = set()
    for reviewer in document["reviewers"]:
        if reviewer["reviewer_id"] in reviewer_ids:
            errors.append("learning reviewer ids must be unique")
        reviewer_ids.add(reviewer["reviewer_id"])
        for prefix in ("identity", "independence"):
            try:
                _verify_file(
                    root,
                    reviewer[f"{prefix}_evidence_path"],
                    reviewer[f"{prefix}_evidence_sha256"],
                )
            except LearningFeasibilityError as exc:
                errors.append(str(exc))
    expected_shape = {
        ("baseline", "baseline"),
        ("player", "immediate"),
        ("player", "seven_day"),
        ("source_reading", "immediate"),
        ("source_reading", "seven_day"),
    }
    sequence_counts = Counter(
        participant["sequence"] for participant in document["participants"]
    )
    if set(sequence_counts) != {"player_first", "source_reading_first"} or abs(
        sequence_counts["player_first"]
        - sequence_counts["source_reading_first"]
    ) > 1:
        errors.append(
            "learning condition order must be counterbalanced across both sequences"
        )
    for participant in document["participants"]:
        if participant["participant_id"] in participant_ids:
            errors.append("learning participant ids must be unique")
        participant_ids.add(participant["participant_id"])
        try:
            _verify_file(
                root,
                participant["consent_evidence_path"],
                participant["consent_evidence_sha256"],
            )
        except LearningFeasibilityError as exc:
            errors.append(str(exc))
        shape = {(task["condition"], task["timepoint"]) for task in participant["tasks"]}
        if shape != expected_shape:
            errors.append("each learner must retain baseline and both immediate/seven-day condition tasks")
        try:
            session_completed = _time(participant["session_completed_at"])
        except LearningFeasibilityError as exc:
            errors.append(str(exc))
            session_completed = None
        for task in participant["tasks"]:
            if task["task_id"] in task_ids:
                errors.append("learning task ids must be globally unique")
            task_ids.add(task["task_id"])
            if task["status"] == "OBSERVED":
                if (
                    task["completed_at"] is None
                    or
                    task["duration_seconds"] is None
                    or task["help_used"] is None
                    or task["artifact_path"] is None
                    or task["artifact_sha256"] is None
                    or len(task["reviews"]) != 2
                ):
                    errors.append("observed learning tasks require artifact, burden, help, and two reviews")
                else:
                    try:
                        completed = _time(task["completed_at"])
                        if session_completed is not None:
                            if task["timepoint"] == "baseline" and completed > session_completed:
                                errors.append("learning baseline task occurred after the learning session")
                            if task["timepoint"] == "immediate" and not (
                                session_completed
                                <= completed
                                <= session_completed + timedelta(days=1)
                            ):
                                errors.append("learning immediate task falls outside its one-day window")
                            if task["timepoint"] == "seven_day" and not (
                                session_completed + timedelta(days=6)
                                <= completed
                                <= session_completed + timedelta(days=10)
                            ):
                                errors.append("learning delayed task falls outside its six-to-ten-day window")
                    except LearningFeasibilityError as exc:
                        errors.append(str(exc))
                    try:
                        _verify_file(root, task["artifact_path"], task["artifact_sha256"])
                    except LearningFeasibilityError as exc:
                        errors.append(str(exc))
                    reviewers = [item["reviewer_id"] for item in task["reviews"]]
                    if len(set(reviewers)) != 2:
                        errors.append("learning task reviews require two distinct reviewers")
                    if not set(reviewers).issubset(reviewer_ids):
                        errors.append(
                            "learning task review uses a reviewer without verified identity and independence evidence"
                        )
            elif any(
                value is not None
                for value in (
                    task["completed_at"],
                    task["duration_seconds"],
                    task["help_used"],
                    task["artifact_path"],
                    task["artifact_sha256"],
                )
            ) or task["reviews"]:
                errors.append("missing or withdrawn learning tasks must not carry result evidence")
            if participant["withdrawn"] and any(
                task["status"] not in {"WITHDRAWN", "OBSERVED"}
                for task in participant["tasks"]
            ):
                errors.append("withdrawn participants must retain completed tasks and mark remaining tasks withdrawn")
    return errors


def analyze(document: dict[str, Any], source_path: Path) -> dict[str, Any]:
    if errors := validate_observations(document, source_path):
        raise LearningFeasibilityError("; ".join(errors))
    tasks = [task for participant in document["participants"] for task in participant["tasks"]]
    summaries = []
    for condition, timepoint in (
        ("baseline", "baseline"),
        ("player", "immediate"),
        ("player", "seven_day"),
        ("source_reading", "immediate"),
        ("source_reading", "seven_day"),
    ):
        selected = [
            task
            for task in tasks
            if task["condition"] == condition and task["timepoint"] == timepoint
        ]
        observed = [task for task in selected if task["status"] == "OBSERVED"]
        scores: list[float] = []
        differences: list[float] = []
        durations: list[float] = []
        for task in observed:
            reviewer_totals = [sum(review["scores"].values()) for review in task["reviews"]]
            scores.append(sum(reviewer_totals) / len(reviewer_totals))
            differences.append(abs(reviewer_totals[0] - reviewer_totals[1]))
            durations.append(float(task["duration_seconds"]))
        summaries.append(
            {
                "condition": condition,
                "timepoint": timepoint,
                "denominator": len(selected),
                "observed_count": len(observed),
                "missing_or_withdrawn_count": len(selected) - len(observed),
                "mean_primary_score": sum(scores) / len(scores) if scores else None,
                "minimum_primary_score": min(scores) if scores else None,
                "maximum_primary_score": max(scores) if scores else None,
                "mean_reviewer_absolute_difference": (
                    sum(differences) / len(differences) if differences else None
                ),
                "mean_duration_seconds": (
                    sum(durations) / len(durations) if durations else None
                ),
                "help_use_count": sum(task["help_used"] is True for task in observed),
            }
        )
    result = {
        "schema_version": "1.0",
        "evidence_class": "learning-feasibility-analysis",
        "qualification_claim_allowed": False,
        "candidate_commit": document["candidate_commit"],
        "topic_sha256": document["topic_sha256"],
        "observations_sha256": digest(document),
        "participant_count": len(document["participants"]),
        "withdrawal_count": sum(item["withdrawn"] for item in document["participants"]),
        "task_status_counts": dict(sorted(Counter(item["status"] for item in tasks).items())),
        "condition_timepoint_summaries": summaries,
        "claim_limit": (
            "This feasibility analysis preserves withdrawals and missing follow-up and "
            "reports blinded rubric distributions, burden, and help use. It is not a "
            "powered efficacy result, certification, generalized mastery claim, or coaching-product release evidence."
        ),
    }
    result["result_sha256"] = digest(result)
    if errors := schema_errors(result, RESULT_SCHEMA):
        raise LearningFeasibilityError(
            "learning result schema failure: " + "; ".join(errors)
        )
    return result


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise LearningFeasibilityError("learning result output is create-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = json.loads(args.observations.read_text(encoding="utf-8"))
        result = analyze(document, args.observations)
        write_new(args.output, result)
        print(json.dumps({"status": "pass", "output": str(args.output), "result_sha256": result["result_sha256"], "qualification_claim_allowed": False}, indent=2))
        return 0
    except (json.JSONDecodeError, OSError, LearningFeasibilityError) as exc:
        print(json.dumps({"status": "fail", "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
