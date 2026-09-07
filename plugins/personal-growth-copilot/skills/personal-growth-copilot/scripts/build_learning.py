#!/usr/bin/env python3
"""Validate a source-grounded topic pack and build a portable offline lesson."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator, FormatChecker

ASSETS = Path(__file__).resolve().parents[1] / "assets/learning"
MAX_PACK_BYTES = 500_000


def concept_order(pack: dict) -> list[str]:
    nodes = {c["id"]: c for c in pack["concepts"]}
    result = []
    visiting = set()

    def visit(node):
        if node in visiting:
            raise ValueError("Prerequisite cycle.")
        if node in result:
            return
        if node not in nodes:
            raise ValueError("Unknown prerequisite.")
        visiting.add(node)
        for parent in nodes[node]["prerequisites"]:
            visit(parent)
        visiting.remove(node)
        result.append(node)

    for node in nodes:
        visit(node)
    return result


def validate_pack(pack: object) -> list[str]:
    schema = json.loads((ASSETS / "topic-pack.schema.json").read_text())
    errors = [
        f"{list(e.path)}: {e.message}"
        for e in Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(pack)
    ]
    if errors:
        return errors
    sources = {s["id"] for s in pack["sources"]}
    if len(sources) != len(pack["sources"]):
        errors.append("Duplicate source IDs.")
    if len({c["id"] for c in pack["concepts"]}) != len(pack["concepts"]):
        errors.append("Duplicate concept IDs.")
    if sorted(pack["review_days"]) != pack["review_days"]:
        errors.append("Review intervals must increase.")
    for source in pack["sources"]:
        try:
            url = urlsplit(source["url"])
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or re.search(r"[\s\\\x00-\x1f]", source["url"])
            ):
                errors.append(
                    "Source URL must be an absolute HTTPS URL without credentials or whitespace."
                )
        except ValueError:
            errors.append("Invalid source URL.")
        if date.fromisoformat(source["accessed"]) > date.today():
            errors.append("Source inspection date is in the future.")
    for c in pack["concepts"]:
        if not set(c["source_ids"]) <= sources:
            errors.append("Unknown source reference.")
        if len({x["id"] for x in c["writing"]["criteria"]}) != len(
            c["writing"]["criteria"]
        ):
            errors.append("Duplicate rubric IDs.")
        prompts = []
        for question in c["questions"].values():
            ids = [x["id"] for x in question["choices"]]
            if len(set(ids)) != len(ids) or question["correct"] not in ids:
                errors.append("Invalid question answer IDs.")
            prompts.append(question["prompt"])
        if len(set(prompts)) != len(prompts):
            errors.append(
                "Use distinct diagnostic, practice, transfer, and review prompts."
            )
    try:
        concept_order(pack)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def load_pack(raw: bytes) -> dict:
    if len(raw) > MAX_PACK_BYTES:
        raise ValueError("Topic pack exceeds 500 KB.")
    pack = json.loads(raw.decode("utf-8"))
    errors = validate_pack(pack)
    if errors:
        raise ValueError("\n".join(errors))
    return pack


def render(raw: bytes) -> str:
    pack = load_pack(raw)
    digest = hashlib.sha256(raw).hexdigest()
    by_id = {c["id"]: c for c in pack["concepts"]}
    pack["concepts"] = [by_id[k] for k in concept_order(pack)]
    payload = (
        json.dumps(
            {"pack": pack, "digest": digest}, ensure_ascii=False, separators=(",", ":")
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    css = (ASSETS / "player.css").read_text()
    scripts = [(ASSETS / p).read_text() for p in ["core.js", "player.js"]]

    def policy_hash(text):
        return (
            "'sha256-"
            + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
            + "'"
        )

    csp = (
        "default-src 'none'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'; script-src "
        + " ".join(policy_hash(s) for s in scripts)
        + "; style-src "
        + policy_hash(css)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}"><meta name="referrer" content="no-referrer">
<title>{html.escape(pack['title'])} · Learning Lab</title><style>{css}</style></head>
<body><a class="skip" href="#workspace">Skip to practice</a>
<header><a class="wordmark" href="#">Personal Growth <span> / Learning Lab</span></a><span class="edition">TOPIC {html.escape(pack['version'])}</span></header>
<div class="layout"><nav id="navigation" aria-label="Lesson navigation"></nav><main id="workspace" tabindex="-1"></main><aside id="context" aria-label="Evidence and progress"></aside></div>
<footer><div id="storage"></div><div class="file-actions"><button id="export">Export progress</button><label class="file-button" for="import">Import progress</label><input id="import" type="file" accept="application/json,.json"><button id="clear">Clear progress</button></div><p id="notice" role="status" aria-live="polite"></p></footer>
<noscript>This offline lesson requires JavaScript. Use the accompanying topic JSON and learning reference with a tutor if JavaScript is unavailable.</noscript>
<script type="application/json" id="topic-data">{payload}</script>
<script>{scripts[0]}</script><script>{scripts[1]}</script></body></html>\n"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pack", type=Path, default=ASSETS / "requirements-writing.json"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="New HTML file to create; existing different bytes are never overwritten.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate only, or compare an existing --out without writing.",
    )
    args = parser.parse_args()
    try:
        raw = args.pack.read_bytes()
        pack = load_pack(raw)
        if args.out:
            artifact = render(raw).encode()
            if args.out.is_symlink():
                raise ValueError("Output may not be a symlink.")
            if args.check:
                if args.out.read_bytes() != artifact:
                    raise ValueError("Generated lesson differs from output.")
            elif args.out.exists():
                if args.out.read_bytes() != artifact:
                    raise ValueError(
                        "Output exists with different bytes; choose a new output path."
                    )
            else:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                with args.out.open("xb") as f:
                    f.write(artifact)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "topic": pack["id"],
                    "version": pack["version"],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "output": str(args.out) if args.out else None,
                }
            )
        )
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
