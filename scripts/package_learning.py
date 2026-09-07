#!/usr/bin/env python3
"""Create a reproducible, self-contained learning candidate ZIP. Never include user progress."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot"


def package_bytes() -> bytes:
    spec = importlib.util.spec_from_file_location(
        "package_learning_builder", SKILL / "scripts/build_learning.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    raw = (SKILL / "assets/learning/requirements-writing.json").read_bytes()
    files = {"requirements-writing.html": builder.render(raw).encode()}
    # Explicit source folders only. No learner records, reports, environment, caches,
    # transcripts, browser data, test fixtures, or local qualification receipts.
    inventory = json.loads((ROOT / "release/learning-package-files.json").read_text())
    if inventory.get("schema_version") != "1.0":
        raise ValueError("Unsupported package inventory.")
    names = inventory["files"]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate package inventory path.")
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe package inventory path.")
        path = SKILL / relative
        if path.resolve() != path.absolute() or not path.is_file():
            raise ValueError("Package file must be a regular, non-symlink source file.")
        files["personal-growth-copilot/" + name] = path.read_bytes()
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    files[
        "README.txt"
    ] = b"""Open requirements-writing.html in a modern browser. No server or account is needed.
Progress starts in the tab only. Enable device saving or export before closing.
Source links open only when selected. Written exercises are not automatically graded.

The personal-growth-copilot folder is a complete explicit-invocation Agent Skill.
Import it with your compatible host's skill installation workflow. The HTML player
works independently of the skill and needs no Python or Node.js installation.

This is a research candidate, not a production-qualified coaching product or an
independent assessment. Read the included acceptance and pilot documents.
Browser storage on file URLs varies; JSON export/import is the portable resume path.
"""
    for name in (
        "LEARNING_RELEASE.md",
        "LEARNING_PILOT.md",
        "TOPIC_PACKS.md",
        "LEARNING_ACCEPTANCE.md",
    ):
        files["docs/" + name] = (ROOT / "docs" / name).read_bytes()
    manifest = {
        "schema_version": "1.0",
        "version": (ROOT / "VERSION").read_text().strip(),
        "claim": "portable-package-integrity-only",
        "files": {p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())},
    }
    files["MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    out = io.BytesIO()
    with zipfile.ZipFile(
        out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = package_bytes()
    if args.out.is_symlink():
        raise ValueError("Output may not be a symlink.")
    if args.out.exists():
        if args.out.read_bytes() != data:
            raise ValueError("Output differs; choose a new filename.")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as f:
            f.write(data)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    )


if __name__ == "__main__":
    main()
