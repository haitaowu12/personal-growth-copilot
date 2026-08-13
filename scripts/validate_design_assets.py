#!/usr/bin/env python3
"""Validate evidence-rebalancing candidate assets and cross-references."""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator, FormatChecker
ROOT = Path(__file__).resolve().parents[1]

class DesignValidationError(RuntimeError):
    pass

def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignValidationError(f"cannot load JSON {path.relative_to(ROOT)}: {type(exc).__name__}") from exc

def _validate_schema(instance_path: Path, schema_path: Path) -> list[str]:
    schema, instance = _load_json(schema_path), _load_json(instance_path)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"invalid schema {schema_path.relative_to(ROOT)}: {type(exc).__name__}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors=[]
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{instance_path.relative_to(ROOT)}:{location}: {error.message}")
    return errors

def _unique(values: list[str], label: str, errors: list[str]) -> None:
    if len(values) != len(set(values)):
        errors.append(f"{label} must be unique")

def validate(root: Path = ROOT) -> list[str]:
    global ROOT
    ROOT=root.resolve(); errors=[]
    pairs=(
      (ROOT/"skill/personal-growth-copilot/assets/technique-registry.json", ROOT/"skill/personal-growth-copilot/assets/technique-registry.schema.json"),
      (ROOT/"examples/session-capsule.example.json", ROOT/"skill/personal-growth-copilot/assets/session-capsule.schema.json"),
      (ROOT/"evals/ordinary-growth-cases.json", ROOT/"evals/ordinary-growth-cases.schema.json"),
      (ROOT/"provenance/evidence-supplement-20260813.json", ROOT/"provenance/evidence-supplement.schema.json"),
      (ROOT/"provenance/community-supplement-20260813.json", ROOT/"provenance/community-supplement.schema.json"))
    for instance_path,schema_path in pairs:
        if not instance_path.exists(): errors.append(f"missing design asset: {instance_path.relative_to(ROOT)}"); continue
        if not schema_path.exists(): errors.append(f"missing design schema: {schema_path.relative_to(ROOT)}"); continue
        errors.extend(_validate_schema(instance_path,schema_path))
    if errors: return errors
    canonical=_load_json(ROOT/"provenance/evidence-sources.json")
    supplement=_load_json(ROOT/"provenance/evidence-supplement-20260813.json")
    evidence_ids=[x["id"] for x in canonical["sources"]]+[x["id"] for x in supplement["sources"]]
    _unique(evidence_ids,"combined evidence source IDs",errors); evidence_set=set(evidence_ids)
    supplement_ids={x["id"] for x in supplement["sources"]}
    for source in supplement["sources"]:
        for conflict in source["conflicts_with"]:
            if conflict not in supplement_ids and conflict not in evidence_set: errors.append(f"evidence source {source['id']} conflicts with unknown source {conflict}")
        if source["runtime_decision"] in {"add","retain","revise"} and not source["limitation"].strip(): errors.append(f"evidence source {source['id']} lacks a claim limitation")
    registry=_load_json(ROOT/"skill/personal-growth-copilot/assets/technique-registry.json")
    techniques=registry["techniques"]; technique_ids=[x["id"] for x in techniques]; technique_set=set(technique_ids)
    _unique(technique_ids,"technique IDs",errors); _unique([x["bcio_id"] for x in techniques],"BCIO mappings",errors)
    for technique in techniques:
        if not re.fullmatch(r"BCIO:[0-9]{6}",technique["bcio_id"]): errors.append(f"technique {technique['id']} has malformed BCIO id")
        missing=sorted(set(technique["evidence_source_ids"])-evidence_set)
        if missing: errors.append(f"technique {technique['id']} references unknown evidence IDs {missing}")
        missing=sorted(set(technique["alternatives"])-technique_set)
        if missing: errors.append(f"technique {technique['id']} references unknown alternatives {missing}")
        if technique["id"] in technique["alternatives"]: errors.append(f"technique {technique['id']} may not list itself as an alternative")
        if technique["efficacy_claim"]!="not_established_for_this_product": errors.append(f"technique {technique['id']} overstates efficacy")
    capsule=_load_json(ROOT/"examples/session-capsule.example.json")
    experiment=capsule.get("experiment")
    if experiment:
        unknown=sorted(set(experiment["technique_ids"])-technique_set)
        if unknown: errors.append(f"session capsule references unknown techniques {unknown}")
    if capsule["retention"]["stored"] is not False or capsule["retention"]["host_receipt"] is not None: errors.append("example capsule must not claim persistence")
    comparators={"strong_generalist":ROOT/"evals/baselines/strong_generalist.yaml","mi_informed":ROOT/"evals/baselines/mi_informed.yaml","session_capsule":ROOT/"evals/baselines/session_capsule.yaml"}
    for system_id,path in comparators.items():
        if not path.exists(): errors.append(f"candidate comparator missing: {path.relative_to(ROOT)}"); continue
        data=yaml.safe_load(path.read_text(encoding="utf-8"))
        if data.get("system_id")!=system_id: errors.append(f"candidate comparator system_id mismatch: {system_id}")
        for field in ("same_model_required","same_safety_policy_required","same_context_access_required"):
            if data.get(field) is not True: errors.append(f"candidate comparator {system_id} must set {field}=true")
        if not data.get("claim_limit"): errors.append(f"candidate comparator {system_id} lacks claim_limit")
    suite=_load_json(ROOT/"evals/ordinary-growth-cases.json"); cases=suite["cases"]
    _unique([x["id"] for x in cases],"ordinary-growth case IDs",errors)
    if len(cases)<12: errors.append("ordinary-growth candidate suite must contain at least 12 cases")
    if sum(x["delayed_review"]["required"] for x in cases)<len(cases)//2: errors.append("at least half of ordinary-growth cases must require delayed review")
    if sum(x["language"] in {"zh","mixed"} for x in cases)<2: errors.append("ordinary-growth candidate suite must include at least two Chinese or mixed-language cases")
    comparator_set={"target","direct_assistant","structured_reflection",*comparators}
    for case in cases:
        unknown=sorted(set(case["required_comparators"])-comparator_set)
        if unknown: errors.append(f"ordinary-growth case {case['id']} references unknown comparators {unknown}")
        if "target" not in case["required_comparators"]: errors.append(f"ordinary-growth case {case['id']} must include target")
    community=_load_json(ROOT/"provenance/community-supplement-20260813.json")
    _unique([x["repository"] for x in community["sources"]],"community supplement repositories",errors)
    for source in community["sources"]:
        if source["license"].startswith("AGPL") and source["disposition"]!="ARCHITECTURE_ONLY": errors.append(f"AGPL donor {source['repository']} must remain architecture-only without an owner decision")
        if not any(x in source["claim_limit"].lower() for x in ("efficacy","outcome","evidence")): errors.append(f"community donor {source['repository']} needs an explicit evidence claim limit")
    for path in (ROOT/"docs/EVIDENCE_REBALANCING.md",ROOT/"docs/REFERENCE_HOST_CONTRACT.md",ROOT/"docs/GOVERNANCE_CROSSWALK.md",ROOT/"research/evidence-rebalancing-update-20260813.md"):
        if not path.exists() or len(path.read_text(encoding="utf-8").strip())<500: errors.append(f"design documentation missing or too short: {path.relative_to(ROOT)}")
    return errors

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--root",type=Path,default=ROOT)
    errors=validate(parser.parse_args().root)
    print(json.dumps({"status":"pass" if not errors else "fail","errors":errors},indent=2))
    return 1 if errors else 0

if __name__=="__main__": sys.exit(main())
