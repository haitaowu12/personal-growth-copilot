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
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
