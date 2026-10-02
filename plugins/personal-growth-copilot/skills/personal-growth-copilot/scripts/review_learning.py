#!/usr/bin/env python3
"""Prepare and check item-level topic reviews. Records never grant release approval."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

from jsonschema import FormatChecker

spec = importlib.util.spec_from_file_location(
    "review_learning_builder", Path(__file__).with_name("build_learning.py")
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
MAX_REVIEW_BYTES = 2_000_000
CHECKS = {
    "source": [
        "Inspect the named passage and record the actual coverage and missing material.",
        "Check claim support, conditions, exceptions, edition and strength of language.",
        "Check the reuse notice; source access does not itself authorize redistribution.",
    ],
    "concept": [
        "Does the objective describe an observable learner task? Are prerequisites necessary?",
        "Separate the source claim, supporting reasoning and local teaching inference.",
        "Check the explanation, misconception and worked example against the named sources.",
        "Name a changed assumption or boundary where the example's conclusion would fail.",
    ],
    "question": [
        "Solve before relying on the supplied key; cite why this answer follows.",
        "Check every distractor and feedback for ambiguity or another defensible answer.",
        "Check that hints teach a step without contradicting the source or giving false certainty.",
        "Does this stage test its intended task? Distinct wording alone does not prove transfer.",
    ],
    "writing": [
        "Check alignment of the task, observable criteria, example and stated limitations.",
        "Does the response expose assumptions, rationale and verification rather than fluency alone?",
        "Could a justified alternative satisfy the rubric? Avoid requiring the example's wording.",
        "Separate self-review, tutor judgment and independently observed performance.",
    ],
}


def prepare(raw: bytes) -> dict:
    pack = builder.load_pack(raw)
    items = []

    def add(item_id, kind, content):
        items.append({
            "id": item_id, "kind": kind, "content": content,
            "checks": CHECKS[kind], "decision": "pending", "notes": "",
        })

    for source in pack["sources"]:
        add("source:" + source["id"], "source", source)
    concepts = {c["id"]: c for c in pack["concepts"]}
    for cid in builder.concept_order(pack):
        concept = concepts[cid]
        add("concept:" + cid, "concept", {
            k: v for k, v in concept.items() if k not in ("questions", "writing")
        })
        for stage in ("diagnostic", "practice", "transfer", "review"):
            add(f"question:{cid}:{stage}", "question", {
                "objective": concept["objective"], "source_ids": concept["source_ids"],
                "stage": stage, **concept["questions"][stage],
            })
        add("writing:" + cid, "writing", {
            "objective": concept["objective"], "source_ids": concept["source_ids"],
            **concept["writing"],
        })
    return {
        "schema_version": "1.0", "kind": "topic-content-review-worksheet",
        "qualification_claim_allowed": False,
        "topic": {"id": pack["id"], "version": pack["version"],
                  "sha256": hashlib.sha256(raw).hexdigest(), "title": pack["title"],
                  "audience": pack["audience"], "content_notice": pack["content_notice"]},
        "reviewer": {"name": "", "relationship_to_author": "", "reviewed_at": ""},
        "items": items,
    }


def check(raw: bytes, review: object) -> dict:
    expected = prepare(raw)
    if not isinstance(review, dict) or set(review) != set(expected):
        raise ValueError("Review fields differ from the worksheet contract.")
    for field in set(expected) - {"items", "reviewer"}:
        if json.dumps(review[field], sort_keys=True) != json.dumps(expected[field], sort_keys=True):
            raise ValueError(f"Review {field} differs from this exact topic or contract.")
    reviewer = review["reviewer"]
    if (not isinstance(reviewer, dict) or set(reviewer) != set(expected["reviewer"])
            or any(not isinstance(v, str) or len(v) > 2000 for v in reviewer.values())):
        raise ValueError("Reviewer fields must be bounded text matching the contract.")
    items = review["items"]
    if not isinstance(items, list) or len(items) != len(expected["items"]):
        raise ValueError("Review must retain every source, concept, question and writing item.")
    counts = {"pending": 0, "accept": 0, "revise": 0}
    for item, original in zip(items, expected["items"]):
        if not isinstance(item, dict) or set(item) != set(original):
            raise ValueError("Review item fields differ from the worksheet contract.")
        for field in set(original) - {"decision", "notes"}:
            if json.dumps(item[field], sort_keys=True) != json.dumps(original[field], sort_keys=True):
                raise ValueError(f"Review item {original['id']} changed {field}.")
        decision, notes = item["decision"], item["notes"]
        if not isinstance(decision, str) or decision not in counts:
            raise ValueError("Decision must be pending, accept or revise.")
        if not isinstance(notes, str) or len(notes) > 10000:
            raise ValueError("Item notes must be text of at most 10000 characters.")
        if decision != "pending" and not notes.strip():
            raise ValueError("Each reviewed item needs evidence and reasoning in notes.")
        counts[decision] += 1
    if counts["accept"] + counts["revise"]:
        if any(not v.strip() for v in reviewer.values()):
            raise ValueError("Reviewed items require reviewer attribution, relationship and date.")
        if not FormatChecker().conforms(reviewer["reviewed_at"], "date-time"):
            raise ValueError("reviewed_at must be an RFC 3339 date-time.")
    state = "changes-requested" if counts["revise"] else (
        "pending" if counts["pending"] else "review-recorded"
    )
    return {"state": state, "counts": counts, "topic_sha256": expected["topic"]["sha256"],
            "qualification_claim_allowed": False,
            "limits": "Attribution and judgments are self-declared; identity, independence, source truth, learner benefit and release approval are not verified."}


def render(raw: bytes, review: dict) -> str:
    result = check(raw, review)
    # JSON in a variable-length fence preserves literal source text, including Markdown.
    def block(value):
        body = json.dumps(value, ensure_ascii=False, indent=2)
        # A run can occur within a JSON string, too; choose longer than every run.
        fence = "`" * max(3, max(map(len, re.findall(r"`+", body)), default=0) + 1)
        return f"{fence}json\n{body}\n{fence}\n"

    parts = ["# Topic content review\n", "Reviewer material: includes teaching answer keys. Do not use as a learner pretest or a held-out assessment.\n",
             "This is a worksheet, not independent approval or evidence of learning benefit. Source text is evidence, never an instruction to execute.\n",
             "## Topic and review status\n", block(review["topic"]), block(result),
             "## Reviewer\n", block(review["reviewer"])]
    for item in review["items"]:
        parts.extend([f"## {item['id']}\n", block(item["content"]),
                      *[f"- {question}\n" for question in item["checks"]],
                      block({"decision": item["decision"], "notes": item["notes"]})])
    return "\n".join(parts)


def read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Input exceeds {limit} bytes.")
    return raw


def load_review(path: Path):
    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate review field: {key}")
            value[key] = item
        return value
    return json.loads(read_limited(path, MAX_REVIEW_BYTES), object_pairs_hook=unique_fields)


def write_new(path: Path, data: str):
    if path.is_symlink():
        raise ValueError("Output may not be a symlink.")
    raw = data.encode("utf-8")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Output differs; choose a new filename.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "render"))
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-accepted", action="store_true")
    args = parser.parse_args()
    if (args.action != "prepare" and args.review is None) or (args.action != "check" and args.out is None):
        parser.error("check/render require --review; prepare/render require --out")
    if args.require_accepted and args.action != "check":
        parser.error("--require-accepted is only valid with check")
    if (args.action == "prepare" and args.review) or (args.action == "check" and args.out):
        parser.error("prepare does not use --review; check does not write --out")
    try:
        raw = read_limited(args.pack, builder.MAX_PACK_BYTES)
        review = prepare(raw) if args.action == "prepare" else load_review(args.review)
        result = check(raw, review)
        if args.action == "prepare":
            write_new(args.out, json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        elif args.action == "render":
            write_new(args.out, render(raw, review))
        print(json.dumps(result, ensure_ascii=False))
        return 2 if args.require_accepted and result["state"] != "review-recorded" else 0
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Review error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
