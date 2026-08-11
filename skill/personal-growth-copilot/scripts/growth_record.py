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
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

POLICIES = {"OFF", "SESSION_ONLY", "CONFIRM_EACH"}
COLLECTIONS = (
    "preferences",
    "goals",
    "hypotheses",
    "experiments",
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


@lru_cache(maxsize=1)
def schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_error(error: Any) -> str:
    return f"{error.json_path}: {error.message} [schema:{error.validator}]"


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


def validate_record(data: Any) -> list[str]:
    """Return canonical-schema and semantic-integrity errors for ``data``."""

    errors = validate_against_schema(data)
    errors.extend(_walk_keys(data))
    if not isinstance(data, dict):
        return errors

    seen_ids: set[str] = set()
    hypothesis_ids: set[str] = set()
    experiment_ids: set[str] = set()
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
                errors.append(f"$.{collection}[{index}].id: duplicate id {item_id}")
                continue
            seen_ids.add(item_id)
            if collection == "hypotheses":
                hypothesis_ids.add(item_id)
            elif collection == "experiments":
                experiment_ids.add(item_id)
            elif collection == "corrections":
                correction_rows.append((index, item))

    experiments = data.get("experiments", [])
    if isinstance(experiments, list):
        for index, item in enumerate(experiments):
            if not isinstance(item, dict):
                continue
            hypothesis_id = item.get("hypothesis_id")
            if hypothesis_id and hypothesis_id not in hypothesis_ids:
                errors.append(
                    f"$.experiments[{index}].hypothesis_id: "
                    f"unknown hypothesis {hypothesis_id}"
                )

    learning = data.get("learning", [])
    if isinstance(learning, list):
        for index, item in enumerate(learning):
            if not isinstance(item, dict):
                continue
            experiment_id = item.get("experiment_id")
            if experiment_id and experiment_id not in experiment_ids:
                errors.append(
                    f"$.learning[{index}].experiment_id: "
                    f"unknown experiment {experiment_id}"
                )

    for index, correction in correction_rows:
        target_id = correction.get("target_id")
        correction_id = correction.get("id")
        if target_id == correction_id:
            errors.append(
                f"$.corrections[{index}].target_id: correction cannot target itself"
            )
        elif isinstance(target_id, str) and target_id not in seen_ids:
            errors.append(
                f"$.corrections[{index}].target_id: unknown target {target_id}"
            )

    return sorted(set(errors))


def empty_record(record_id: str, purpose: str, policy: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "record_id": record_id,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": purpose,
        "memory_policy": policy,
        "boundaries": [],
        "preferences": [],
        "goals": [],
        "hypotheses": [],
        "experiments": [],
        "learning": [],
        "corrections": [],
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
