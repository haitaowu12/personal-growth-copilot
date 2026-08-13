#!/usr/bin/env python3
"""Small vendored-independent skill frontmatter check for CI."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    skill_dir = Path(sys.argv[1])
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        print("invalid SKILL.md frontmatter", file=sys.stderr)
        return 1
    frontmatter = text.split("---\n", 2)[1]
    data = yaml.safe_load(frontmatter)
    if set(data) != {"name", "description"}:
        print("frontmatter must contain only name and description", file=sys.stderr)
        return 1
    if data["name"] != skill_dir.name:
        print("skill name and directory differ", file=sys.stderr)
        return 1
    if not isinstance(data["description"], str) or not data["description"].strip():
        print("description missing", file=sys.stderr)
        return 1
    print("Skill is valid!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
