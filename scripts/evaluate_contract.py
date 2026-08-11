#!/usr/bin/env python3
"""Validate behavioral case coverage without pretending to run model evals."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals/cases.json"
REQUIRED_CATEGORIES = {
    "inquiry",
    "context_model",
    "motivation",
    "goal_design",
    "experiment",
    "review",
    "memory",
    "safety",
    "bilingual",
}
REQUIRED_RISKS = {"low", "medium", "high", "critical"}


def validate_cases() -> list[str]:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    errors: list[str] = []
    cases = data.get("cases")
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must equal 1.0")
    if not isinstance(cases, list):
        return errors + ["cases must be an array"]
    if len(cases) < 30:
        errors.append("at least 30 behavioral cases required")

    ids: set[str] = set()
    categories: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    risks: set[str] = set()
    for index, case in enumerate(cases):
        path = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{path} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{path}.id missing")
        elif case_id in ids:
            errors.append(f"duplicate id: {case_id}")
        else:
            ids.add(case_id)
        category = case.get("category")
        language = case.get("language")
        risk = case.get("risk")
        categories[category] += 1
        languages[language] += 1
        risks.add(risk)
        for key in ("prompt", "mode"):
            if not isinstance(case.get(key), str) or not case[key]:
                errors.append(f"{path}.{key} missing")
        for key in ("must", "must_not"):
            value = case.get(key)
            if not isinstance(value, list) or len(value) < 3 or not all(
                isinstance(item, str) and item for item in value
            ):
                errors.append(f"{path}.{key} needs at least three strings")

    missing_categories = sorted(REQUIRED_CATEGORIES - categories.keys())
    if missing_categories:
        errors.append(f"missing categories: {missing_categories}")
    if languages["zh"] < 4:
        errors.append("at least four Chinese cases required")
    if not REQUIRED_RISKS.issubset(risks):
        errors.append("case set must cover low, medium, high, and critical risk")
    if categories["safety"] < 5:
        errors.append("at least five safety cases required")
    return errors


def main() -> int:
    errors = validate_cases()
    data = json.loads(CASES.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "pass" if not errors else "fail",
                "case_count": len(data.get("cases", [])),
                "note": "Structural contract only; no model responses were executed or scored.",
                "errors": errors,
            },
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
