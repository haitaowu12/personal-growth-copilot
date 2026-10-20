#!/usr/bin/env python3
"""Validate research design assets without executing or qualifying them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

ROOT = Path(__file__).resolve().parents[1]
SKILL = "plugins/personal-growth-copilot/skills/personal-growth-copilot"
RUNTIME_EVIDENCE_INDEX = f"{SKILL}/assets/evidence-source-ids.json"
ASSET_PAIRS = (
    (f"{SKILL}/assets/technique-registry.json", f"{SKILL}/assets/technique-registry.schema.json"),
    ("examples/session-capsule.example.json", f"{SKILL}/assets/session-capsule.schema.json"),
    ("evals/ordinary-growth-cases.json", "evals/ordinary-growth-cases.schema.json"),
    ("provenance/evidence-supplement-20260813.json", "provenance/evidence-supplement.schema.json"),
    ("provenance/community-supplement-20260813.json", "provenance/community-supplement.schema.json"),
)
COMPARATORS = ("strong_generalist", "minimal_visible_model", "mi_informed", "session_capsule")
DOCUMENTS = (
    "docs/EVIDENCE_REBALANCING.md",
    "docs/REFERENCE_HOST_CONTRACT.md",
    "docs/GOVERNANCE_CROSSWALK.md",
    "research/evidence-rebalancing-update-20260813.md",
)


class DesignValidationError(ValueError):
    """An unreadable or malformed checked-in design asset."""


def _read_text(root: Path, relative_path: str) -> str:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DesignValidationError(
            f"cannot read {relative_path}: {type(exc).__name__}"
        ) from exc


def _load_json(root: Path, relative_path: str) -> Any:
    try:
        return json.loads(_read_text(root, relative_path))
    except json.JSONDecodeError as exc:
        raise DesignValidationError(f"invalid JSON: {relative_path}") from exc


def _has_external_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")))
            or _has_external_reference(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_external_reference(item) for item in value)
    return False


def _validate_schema(instance: Any, schema: Any, instance_path: str, schema_path: str) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        return [f"invalid schema: {schema_path}"]
    if _has_external_reference(schema):
        return [f"design schema must use local fragment references only: {schema_path}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    try:
        failures = sorted(validator.iter_errors(instance), key=lambda error: str(list(error.path)))
    except Unresolvable:
        return [f"unresolvable schema reference: {schema_path}"]
    errors = []
    for error in failures:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{instance_path}:{location}: {error.message}")
    return errors


def _unique(values: list[str], label: str, errors: list[str]) -> None:
    if len(values) != len(set(values)):
        errors.append(f"{label} must be unique")


def _validate_comparators(root: Path) -> list[str]:
    errors = []
    for comparator_id in COMPARATORS:
        path = f"evals/comparators/{comparator_id}.yaml"
        if (root / f"evals/baselines/{comparator_id}.yaml").exists():
            errors.append(f"comparator {comparator_id} must not have a duplicate legacy baseline")
        try:
            data = yaml.safe_load(_read_text(root, path))
        except (DesignValidationError, yaml.YAMLError) as exc:
            errors.append(str(exc) if isinstance(exc, DesignValidationError) else f"invalid YAML: {path}")
            continue
        if not isinstance(data, dict):
            errors.append(f"comparator must be a mapping: {path}")
            continue
        required = {
            "schema_version": "1.0",
            "comparator_id": comparator_id,
            "status": "design-only-unexecuted",
            "memory_policy": "READ_ONLY_USER_APPROVED",
        }
        for field, expected in required.items():
            if data.get(field) != expected:
                errors.append(f"comparator {comparator_id} must set {field}={expected}")
        for field in ("same_model_required", "same_safety_policy_required", "same_context_access_required"):
            if data.get(field) is not True:
                errors.append(f"comparator {comparator_id} must set {field}=true")
        for field in ("comparison_role", "claim_limit"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                errors.append(f"comparator {comparator_id} needs a nonempty {field}")
        for field in ("instructions", "method_exclusions"):
            values = data.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                errors.append(f"comparator {comparator_id} needs nonempty {field}")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    assets: dict[str, Any] = {}
    for instance_path, schema_path in ASSET_PAIRS:
        try:
            instance = _load_json(root, instance_path)
            schema = _load_json(root, schema_path)
            errors.extend(_validate_schema(instance, schema, instance_path, schema_path))
            assets[instance_path] = instance
        except DesignValidationError as exc:
            errors.append(str(exc))
    # Cross-reference checks need the shapes established by the schemas above.
    if errors:
        return errors

    try:
        canonical = _load_json(root, "provenance/evidence-sources.json")
        runtime_index = _load_json(root, RUNTIME_EVIDENCE_INDEX)
    except DesignValidationError as exc:
        return [str(exc)]
    if not isinstance(canonical, dict) or not isinstance(canonical.get("sources"), list) or any(
        not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]
        for source in canonical["sources"]
    ):
        return ["canonical evidence sources must contain a list of source objects with IDs"]
    if not isinstance(runtime_index, dict) or not isinstance(runtime_index.get("source_ids"), list) or any(
        not isinstance(source_id, str) or not source_id for source_id in runtime_index["source_ids"]
    ):
        return ["runtime evidence-source index must contain a list of source IDs"]
    _unique(runtime_index["source_ids"], "runtime evidence source IDs", errors)
    runtime_evidence_set = set(runtime_index["source_ids"])
    canonical_evidence_set = {source["id"] for source in canonical["sources"]}
    supplement = assets["provenance/evidence-supplement-20260813.json"]
    evidence_ids = [source["id"] for source in canonical["sources"] + supplement["sources"]]
    _unique(evidence_ids, "combined evidence source IDs", errors)
    evidence_set = set(evidence_ids)
    for source in supplement["sources"]:
        for conflict in source["conflicts_with"]:
            if conflict not in evidence_set:
                errors.append(f"evidence source {source['id']} conflicts with unknown source {conflict}")

    registry = assets[f"{SKILL}/assets/technique-registry.json"]
    if registry["ontology"]["evidence_source_id"] not in evidence_set:
        errors.append("technique ontology references an unknown evidence source")
    techniques = registry["techniques"]
    technique_ids = [technique["id"] for technique in techniques]
    technique_set = set(technique_ids)
    _unique(technique_ids, "technique IDs", errors)
    _unique([technique["bcio_id"] for technique in techniques], "BCIO mappings", errors)
    for technique in techniques:
        # Ontology naming may cite candidate research above; technique citation
        # lists must remain usable by the unchanged growth-record allowlist.
        missing = sorted(set(technique["evidence_source_ids"]) - canonical_evidence_set)
        if missing:
            errors.append(f"technique {technique['id']} references unknown evidence IDs for canonical runtime citations {missing}")
        missing = sorted(set(technique["evidence_source_ids"]) - runtime_evidence_set)
        if missing:
            errors.append(f"technique {technique['id']} references IDs absent from the runtime evidence index {missing}")
        missing = sorted(set(technique["alternatives"]) - technique_set)
        if missing:
            errors.append(f"technique {technique['id']} references unknown alternatives {missing}")
        if technique["id"] in technique["alternatives"]:
            errors.append(f"technique {technique['id']} may not list itself as an alternative")

    capsule = assets["examples/session-capsule.example.json"]
    if capsule["persistence"]["status"] == "confirmed_by_host" or capsule["persistence"]["host_receipt_sha256"] is not None:
        errors.append("example capsule must not claim persistence")
    errors.extend(_validate_comparators(root))

    cases = assets["evals/ordinary-growth-cases.json"]["cases"]
    _unique([case["id"] for case in cases], "ordinary-growth case IDs", errors)
    if 2 * sum(case["delayed_review"]["required"] for case in cases) < len(cases):
        errors.append("at least half of ordinary-growth cases must require delayed review")
    if sum(case["language"] in {"zh", "mixed"} for case in cases) < 2:
        errors.append("ordinary-growth candidate suite must include at least two Chinese or mixed-language cases")
    comparator_set = {"target", "direct_assistant", "structured_reflection", *COMPARATORS}
    for case in cases:
        unknown = sorted(set(case["required_comparators"]) - comparator_set)
        if unknown:
            errors.append(f"ordinary-growth case {case['id']} references unknown comparators {unknown}")
        if "target" not in case["required_comparators"]:
            errors.append(f"ordinary-growth case {case['id']} must include target")

    community = assets["provenance/community-supplement-20260813.json"]
    _unique([source["repository"] for source in community["sources"]], "community supplement repositories", errors)
    for source in community["sources"]:
        if (source["license"].startswith("AGPL") or source["license"].startswith("Mixed:")) and source["disposition"] != "ARCHITECTURE_ONLY":
            errors.append(f"restricted-license donor {source['repository']} must remain architecture-only without an owner decision")
        if not any(word in source["claim_limit"].lower() for word in ("efficacy", "outcome", "evidence")):
            errors.append(f"community donor {source['repository']} needs an explicit evidence claim limit")
    for path in DOCUMENTS:
        try:
            if len(_read_text(root, path).strip()) < 500:
                errors.append(f"design documentation missing or too short: {path}")
        except DesignValidationError as exc:
            errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    errors = validate(parser.parse_args().root)
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
