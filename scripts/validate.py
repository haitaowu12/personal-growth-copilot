#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

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
    if len(cases.get("cases", [])) < 30:
        errors.append("at least 30 evaluation cases required")
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
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
