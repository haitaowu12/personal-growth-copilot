from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/personal-growth-copilot/skills/personal-growth-copilot"


class RuntimeCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example = json.loads((ROOT / "examples/growth-record.example.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((SKILL / "assets/technique-registry.json").read_text(encoding="utf-8"))
        cls.runtime_index = json.loads((SKILL / "assets/evidence-source-ids.json").read_text(encoding="utf-8"))

    def record_with_citation(self, source_id: str) -> dict:
        record = copy.deepcopy(self.example)
        record["evidence"].append({
            "id": "external-source-1",
            "statement": "Synthetic external citation for method review; not evidence of a personal outcome.",
            "source": "UNKNOWN",
            "origin_kind": "EXTERNAL_SOURCE",
            "source_citation_id": source_id,
            "captured_at": "2026-08-10T12:00:00Z",
            "review_at": "2026-08-17T12:00:00Z",
            "context": "Synthetic active-experiment record validation.",
            "status": "active",
        })
        record["hypotheses"][0]["supporting_evidence_ids"].append("external-source-1")
        return record

    def validate_with_real_cli(self, record: dict, expected_status: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-record.json"
            contents = json.dumps(record, ensure_ascii=False).encode("utf-8")
            path.write_bytes(contents)
            completed = subprocess.run(
                [sys.executable, str(SKILL / "scripts/growth_record.py"), "validate", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(path.read_bytes(), contents)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0 if expected_status == "pass" else 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], expected_status)
        return result

    def test_all_registry_citations_validate_in_an_active_record(self) -> None:
        citations = {source for technique in self.registry["techniques"] for source in technique["evidence_source_ids"]}
        self.assertTrue(citations)
        self.assertTrue(citations.issubset(self.runtime_index["source_ids"]))
        for citation in sorted(citations):
            with self.subTest(citation=citation):
                record = self.record_with_citation(citation)
                self.assertEqual(record["experiments"][0]["status"], "active")
                self.assertEqual(self.validate_with_real_cli(record, "pass")["errors"], [])

    def test_research_taxonomy_and_unknown_citations_are_rejected(self) -> None:
        technique = self.registry["techniques"][0]
        for citation in (
            self.registry["ontology"]["evidence_source_id"],
            technique["id"], technique["bcio_id"], "unregistered-source",
        ):
            with self.subTest(citation=citation):
                self.assertNotIn(citation, self.runtime_index["source_ids"])
                result = self.validate_with_real_cli(self.record_with_citation(citation), "fail")
                self.assertTrue(any("source_citation_id: unknown evidence source" in error for error in result["errors"]), result)

    def test_external_citations_cannot_be_attached_to_user_statements(self) -> None:
        record = copy.deepcopy(self.example)
        record["evidence"][0]["source_citation_id"] = self.registry["techniques"][0]["evidence_source_ids"][0]
        result = self.validate_with_real_cli(record, "fail")
        self.assertTrue(any("only external evidence may cite" in error for error in result["errors"]), result)

    def test_hypothesis_references_record_items_instead_of_source_citations(self) -> None:
        citation = self.registry["techniques"][0]["evidence_source_ids"][0]
        record = self.record_with_citation(citation)
        record["hypotheses"][0]["supporting_evidence_ids"] = [citation]
        result = self.validate_with_real_cli(record, "fail")
        self.assertTrue(any("unknown evidence" in error for error in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
