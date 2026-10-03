from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


reviewer = module("learning_review", SKILL / "scripts/review_learning.py")


class LearningReviewTests(unittest.TestCase):
    def setUp(self):
        self.raw = (SKILL / "assets/learning/requirements-writing.json").read_bytes()
        self.review = reviewer.prepare(self.raw)

    def accepted(self):
        record = copy.deepcopy(self.review)
        record["reviewer"] = {"name": "Synthetic fixture", "relationship_to_author": "Test only; not independent evidence",
                              "reviewed_at": "2026-10-02T12:00:00Z"}
        for item in record["items"]:
            item.update(decision="accept", notes="Synthetic validation fixture, no actual source review.")
        return record

    def test_complete_unapproved_inventory_in_prerequisite_order(self):
        self.assertEqual(self.review, reviewer.prepare(self.raw))
        result = reviewer.check(self.raw, self.review)
        self.assertEqual(result["counts"], {"pending": 21, "accept": 0, "revise": 0})
        self.assertFalse(result["qualification_claim_allowed"])
        pack = json.loads(self.raw)
        contents = {i["id"]: i["content"] for i in self.review["items"]}
        for concept in pack["concepts"]:
            for stage, question in concept["questions"].items():
                content = contents[f"question:{concept['id']}:{stage}"]
                self.assertEqual(content["choices"], question["choices"])
                self.assertEqual(content["correct"], question["correct"])
            self.assertEqual(contents[f"writing:{concept['id']}"]["criteria"], concept["writing"]["criteria"])

    def test_all_acceptance_remains_nonqualifying_and_revision_takes_precedence(self):
        record = self.accepted()
        self.assertEqual(reviewer.check(self.raw, record)["state"], "review-recorded")
        self.assertFalse(reviewer.check(self.raw, record)["qualification_claim_allowed"])
        record["items"][0]["decision"] = "revise"
        record["items"][1]["decision"] = "pending"
        self.assertEqual(reviewer.check(self.raw, record)["state"], "changes-requested")

    def test_returned_checklists_cannot_change_validation_contract(self):
        original = copy.deepcopy(reviewer.CHECKS)
        try:
            self.review["items"][0]["checks"].clear()
            self.assertEqual(reviewer.CHECKS, original)
            with self.assertRaises(ValueError):
                reviewer.check(self.raw, self.review)
            fresh = reviewer.prepare(self.raw)
            self.assertEqual(fresh["items"][0]["checks"], original["source"])
        finally:
            reviewer.CHECKS.clear()
            reviewer.CHECKS.update(original)

    def test_duplicate_topic_keys_rejected_before_review_or_html(self):
        cases = (
            self.raw.replace(b'"id": "requirements-writing",',
                             b'"id": "wrong-first-value", "id": "requirements-writing",', 1),
            self.raw.replace(b'"correct": "a",', b'"correct": "b", "correct": "a",', 1),
        )
        for raw in cases:
            self.assertNotEqual(raw, self.raw)
            for consume in (reviewer.prepare, reviewer.builder.render):
                with self.subTest(consumer=consume.__name__), self.assertRaisesRegex(ValueError, "Duplicate topic field"):
                    consume(raw)

    def test_changed_topic_bytes_invalidate_review_even_with_same_version(self):
        with self.assertRaisesRegex(ValueError, "exact topic"):
            reviewer.check(self.raw + b"\n", self.accepted())

    def test_omitted_duplicated_reordered_and_edited_items_rejected(self):
        mutations = [
            lambda r: r["items"].pop(),
            lambda r: r["items"].__setitem__(1, copy.deepcopy(r["items"][0])),
            lambda r: r["items"].reverse(),
            lambda r: r["items"][4]["content"].update(correct="fabricated"),
            lambda r: r["items"][0]["checks"].clear(),
            lambda r: r.update(qualification_claim_allowed=True),
            lambda r: r.update(qualification_claim_allowed=0),
            lambda r: r["items"][0].update(approved=True),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                record = copy.deepcopy(self.review)
                mutate(record)
                with self.assertRaises(ValueError):
                    reviewer.check(self.raw, record)

    def test_judgments_require_attribution_and_reasoning(self):
        for field in ("name", "relationship_to_author", "reviewed_at"):
            record = self.accepted()
            record["reviewer"][field] = " "
            with self.subTest(field=field), self.assertRaises(ValueError):
                reviewer.check(self.raw, record)
        record = self.accepted()
        record["items"][0]["notes"] = "  "
        with self.assertRaises(ValueError):
            reviewer.check(self.raw, record)
        record = self.accepted()
        record["reviewer"]["reviewed_at"] = "not a date"
        with self.assertRaises(ValueError):
            reviewer.check(self.raw, record)

    def test_malformed_records_fail_with_value_error(self):
        for malformed in ([], None, {}, "accepted"):
            with self.subTest(value=malformed), self.assertRaises(ValueError):
                reviewer.check(self.raw, malformed)
        for field, value in (("decision", []), ("notes", {}), ("notes", "x" * 10001)):
            record = copy.deepcopy(self.review)
            record["items"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                reviewer.check(self.raw, record)

    def test_invalid_pack_never_produces_review(self):
        pack = json.loads(self.raw)
        pack["concepts"][0]["source_ids"] = ["absent"]
        with self.assertRaises(ValueError):
            reviewer.prepare(json.dumps(pack).encode())

    def test_literal_render_preserves_notes_and_cannot_close_code_fence(self):
        record = self.accepted()
        record["items"][0]["notes"] = '```\n# Not a heading\n<script>do not execute</script>\n````'
        rendered = reviewer.render(self.raw, record)
        self.assertIn("`````json", rendered)
        self.assertIn(json.dumps(record["items"][0]["notes"]), rendered)
        self.assertEqual(rendered.count("## question:"), 12)
        self.assertEqual(rendered.count("## writing:"), 3)

    def test_reject_duplicate_fields_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text('{"items": [], "items": []}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                reviewer.load_review(path)
            path.write_bytes(b"x" * (reviewer.MAX_REVIEW_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                reviewer.load_review(path)

    def test_output_preserves_existing_work_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            reviewer.write_new(path, "original")
            reviewer.write_new(path, "original")
            with self.assertRaises(ValueError):
                reviewer.write_new(path, "changed")
            self.assertEqual(path.read_text(), "original")
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                reviewer.write_new(link, "original")

    def test_packaged_cli_works_without_repo_and_does_not_bundle_reviews(self):
        packager = module("review_package", ROOT / "scripts/package_learning.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(io.BytesIO(packager.package_bytes())) as archive:
                self.assertFalse(any(name.endswith("review.json") for name in archive.namelist()))
                archive.extractall(root)
            skill = root / "personal-growth-copilot"
            self.assertTrue((skill / "references/topic-authoring.md").is_file())
            command = [sys.executable, str(skill / "scripts/review_learning.py")]
            pack_arg = ["--pack", str(skill / "assets/learning/requirements-writing.json")]
            review = root / "review.json"

            def run(*args):
                return subprocess.run(command + list(args) + pack_arg, cwd=root, capture_output=True, text=True)

            prepared = run("prepare", "--out", str(review))
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(json.loads(prepared.stdout)["counts"]["pending"], 21)
            checked = run("check", "--review", str(review), "--require-accepted")
            self.assertEqual(checked.returncode, 2, checked.stderr)
            review.write_text(json.dumps(self.accepted()))
            checked = run("check", "--review", str(review), "--require-accepted")
            self.assertEqual(checked.returncode, 0, checked.stderr)
            rendered = run("render", "--review", str(review), "--out", str(root / "review.md"))
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            review.write_text("{}")
            invalid = run("check", "--review", str(review))
            self.assertEqual(invalid.returncode, 1)
            self.assertNotIn("Traceback", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
