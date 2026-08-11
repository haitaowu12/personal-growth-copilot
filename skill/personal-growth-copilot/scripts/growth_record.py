#!/usr/bin/env python3
"""Create, validate, and summarize portable Personal Growth Copilot records.

This utility never modifies an existing record. A host must separately obtain
the user's confirmation before replacing or merging persisted data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICIES = {"OFF", "SESSION_ONLY", "CONFIRM_EACH"}
SOURCES = {
    "USER-REPORTED",
    "OBSERVED-IN-CHAT",
    "HYPOTHESIS",
    "ALTERNATIVE",
    "UNKNOWN",
    "CORRECTION",
}
TOP_LEVEL = {
    "schema_version",
    "record_id",
    "updated_at",
    "purpose",
    "memory_policy",
    "boundaries",
    "preferences",
    "goals",
    "hypotheses",
    "experiments",
    "learning",
    "corrections",
}
REQUIRED = {
    "schema_version",
    "record_id",
    "updated_at",
    "memory_policy",
    "goals",
    "hypotheses",
    "experiments",
    "learning",
    "corrections",
}
COLLECTIONS = ("preferences", "goals", "hypotheses", "experiments", "learning", "corrections")
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


def _is_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


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
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["$: record must be a JSON object"]

    missing = sorted(REQUIRED - data.keys())
    extra = sorted(data.keys() - TOP_LEVEL)
    errors.extend(f"$.{key}: required field missing" for key in missing)
    errors.extend(f"$.{key}: unknown top-level field" for key in extra)

    if data.get("schema_version") != "1.0":
        errors.append("$.schema_version: must equal 1.0")
    if not isinstance(data.get("record_id"), str) or not data.get("record_id", "").strip():
        errors.append("$.record_id: non-empty string required")
    if not _is_datetime(data.get("updated_at")):
        errors.append("$.updated_at: ISO 8601 date-time required")
    if data.get("memory_policy") not in POLICIES:
        errors.append("$.memory_policy: must be OFF, SESSION_ONLY, or CONFIRM_EACH")

    seen_ids: set[str] = set()
    experiment_ids: set[str] = set()
    hypothesis_ids: set[str] = set()

    for collection in COLLECTIONS:
        items = data.get(collection, [])
        if not isinstance(items, list):
            errors.append(f"$.{collection}: must be an array")
            continue
        for index, item in enumerate(items):
            path = f"$.{collection}[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path}: must be an object")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                errors.append(f"{path}.id: non-empty string required")
            elif item_id in seen_ids:
                errors.append(f"{path}.id: duplicate id {item_id}")
            else:
                seen_ids.add(item_id)
                if collection == "experiments":
                    experiment_ids.add(item_id)
                elif collection == "hypotheses":
                    hypothesis_ids.add(item_id)

            source = item.get("source")
            if source is not None and source not in SOURCES:
                errors.append(f"{path}.source: invalid provenance label")

    for index, item in enumerate(data.get("experiments", [])):
        if not isinstance(item, dict):
            continue
        hypothesis_id = item.get("hypothesis_id")
        if hypothesis_id and hypothesis_id not in hypothesis_ids:
            errors.append(
                f"$.experiments[{index}].hypothesis_id: unknown hypothesis {hypothesis_id}"
            )

    for index, item in enumerate(data.get("learning", [])):
        if not isinstance(item, dict):
            continue
        experiment_id = item.get("experiment_id")
        if experiment_id and experiment_id not in experiment_ids:
            errors.append(
                f"$.learning[{index}].experiment_id: unknown experiment {experiment_id}"
            )

    errors.extend(_walk_keys(data))
    return errors


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
