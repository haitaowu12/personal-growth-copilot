#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skill = (ROOT / "skill/personal-growth-copilot/SKILL.md").read_text(
        encoding="utf-8"
    )
    metadata = (
        ROOT / "skill/personal-growth-copilot/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    qualification = json.loads(
        (ROOT / "release/qualification.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "provenance/evidence-sources.json").read_text(encoding="utf-8")
    )
    community = json.loads(
        (ROOT / "provenance/community-sources.json").read_text(encoding="utf-8")
    )
    cases = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
    if "TODO" in skill:
        errors.append("SKILL.md contains TODO")
    if "Use only after explicit invocation" not in skill:
        errors.append("SKILL.md lacks explicit invocation rule")
    if "allow_implicit_invocation: false" not in metadata:
        errors.append("agents/openai.yaml does not disable implicit invocation")
    if qualification.get("release") != version:
        errors.append("release version mismatch")
    if qualification.get("status") != "blocked":
        errors.append("qualification must remain blocked")
    if qualification.get("production_claim_allowed") is not False:
        errors.append("production claim must be false")
    if len(evidence.get("sources", [])) < 15:
        errors.append("at least 15 evidence sources required")
    for index, source in enumerate(evidence.get("sources", [])):
        for field in ("id", "type", "citation", "url", "runtime_use", "limitation"):
            if not source.get(field):
                errors.append(f"evidence source {index} lacks {field}")
    if cases.get("schema_version") != "2.0":
        errors.append("branchable evaluation schema version must equal 2.0")
    if len(cases.get("cases", [])) < 8:
        errors.append("at least eight branchable multi-turn cases required")
    if len(community.get("sources", [])) < 10:
        errors.append("at least 10 pinned community sources required")
    for index, source in enumerate(community.get("sources", [])):
        commit = source.get("commit", "")
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            errors.append(f"community source {index} lacks a full commit hash")
    required_references = {
        "collaborative-inquiry.md",
        "context-model.md",
        "values-goals-and-motivation.md",
        "behavior-change-experiments.md",
        "reflection-and-review.md",
        "memory-and-continuity.md",
        "record-store-contract.md",
        "safety-and-scope.md",
        "bilingual-dialogue.md",
        "evidence-ledger.md",
    }
    reference_dir = ROOT / "skill/personal-growth-copilot/references"
    available = {path.name for path in reference_dir.glob("*.md")}
    if missing := sorted(required_references - available):
        errors.append(f"missing references: {missing}")
    schema = ROOT / "skill/personal-growth-copilot/assets/growth-record.schema.json"
    if not schema.exists():
        errors.append("growth record schema missing")
    required_runtime = {
        ROOT / "skill/personal-growth-copilot/scripts/growth_record.py",
        ROOT / "skill/personal-growth-copilot/scripts/record_store.py",
        ROOT / "requirements/ci.in",
        ROOT / "requirements/ci.txt",
        ROOT / "scripts/lint_eval_manifest.py",
        ROOT / "evals/run.py",
        ROOT / "evals/schema.json",
        ROOT / "evals/config.schema.json",
        ROOT / "evals/results/RESULT_SCHEMA.json",
        ROOT / "evals/configs/conformance.json",
        ROOT / "evals/baselines/direct_assistant.yaml",
        ROOT / "evals/baselines/structured_reflection.yaml",
        ROOT / "safety/safety-state-machine.yaml",
        ROOT / "safety/resource-resolver-interface.md",
        ROOT / "skill/personal-growth-copilot/scripts/safety_runtime.py",
        ROOT / "scripts/run_deterministic_qualification.py",
    }
    for path in sorted(required_runtime):
        if not path.exists():
            errors.append(f"required runtime artifact missing: {path.relative_to(ROOT)}")
    for schema_path in (
        ROOT / "evals/schema.json",
        ROOT / "evals/config.schema.json",
        ROOT / "evals/results/RESULT_SCHEMA.json",
    ):
        try:
            Draft202012Validator.check_schema(
                json.loads(schema_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            errors.append(
                f"invalid JSON Schema {schema_path.relative_to(ROOT)}: {type(exc).__name__}"
            )
    for baseline_name in ("direct_assistant", "structured_reflection"):
        baseline = yaml.safe_load(
            (ROOT / f"evals/baselines/{baseline_name}.yaml").read_text(encoding="utf-8")
        )
        if baseline.get("system_id") != baseline_name:
            errors.append(f"baseline system_id mismatch: {baseline_name}")
        if baseline.get("same_safety_policy_required") is not True:
            errors.append(f"baseline may not weaken safety: {baseline_name}")
        if baseline.get("memory_policy") != "DISABLED":
            errors.append(f"baseline memory must be disabled: {baseline_name}")
    lock_text = (ROOT / "requirements/ci.txt").read_text(encoding="utf-8")
    input_requirements = {
        (match.group(1).lower().replace("_", "-"), match.group(2))
        for line in (ROOT / "requirements/ci.in").read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==([^\s]+)$", line))
    }
    locked_requirements = {
        (match.group(1).lower().replace("_", "-"), match.group(2))
        for line in lock_text.splitlines()
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)", line))
    }
    if not input_requirements.issubset(locked_requirements):
        errors.append("hash lock is missing a direct CI requirement")
    if lock_text.count("--hash=sha256:") < 2 * len(locked_requirements):
        errors.append("CI requirements are not fully hash-locked")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if "--require-hashes" not in workflow:
        errors.append("CI dependency install must enforce requirements hashes")
    if "multiturn-harness-conformance.json" not in workflow:
        errors.append("CI must upload the multi-turn harness conformance artifact")
    if "ubuntu-latest" in workflow:
        errors.append("CI runner label must not float on ubuntu-latest")
    for action in ("actions/checkout@", "actions/setup-python@", "actions/upload-artifact@"):
        lines = [line for line in workflow.splitlines() if action in line]
        if not lines or any(f"{action}v" in line for line in lines):
            errors.append(f"CI action is missing or not commit-pinned: {action}")
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
