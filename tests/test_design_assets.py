from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_design_assets", ROOT / "scripts/validate_design_assets.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REGISTRY = f"{MODULE.SKILL}/assets/technique-registry.json"
CASES = "evals/ordinary-growth-cases.json"
EVIDENCE = "provenance/evidence-supplement-20260813.json"
COMMUNITY = "provenance/community-supplement-20260813.json"
CAPSULE = "examples/session-capsule.example.json"


class DesignAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        paths = {path for pair in MODULE.ASSET_PAIRS for path in pair}
        paths.update(MODULE.DOCUMENTS)
        paths.update(f"evals/comparators/{name}.yaml" for name in MODULE.COMPARATORS)
        paths.add("provenance/evidence-sources.json")
        paths.add(MODULE.RUNTIME_EVIDENCE_INDEX)
        for path in paths:
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, destination)

    @contextmanager
    def changed_json(self, relative_path, mutation):
        path = self.root / relative_path
        original = path.read_bytes()
        data = json.loads(original)
        mutation(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            yield
        finally:
            path.write_bytes(original)

    def assert_rejected(self, path, mutation, expected):
        with self.changed_json(path, mutation):
            errors = MODULE.validate(self.root)
            self.assertTrue(any(expected in error for error in errors), errors)

    def test_current_assets_and_isolated_copy_validate(self):
        self.assertEqual(MODULE.validate(ROOT), [])
        self.assertEqual(MODULE.validate(self.root), [])

    def test_missing_and_malformed_assets_return_errors(self):
        path = self.root / REGISTRY
        original = path.read_bytes()
        for contents, expected in ((None, "cannot read"), (b"{", "invalid JSON"), (b"\xff", "cannot read"), (b"[]", "is not of type")):
            with self.subTest(contents=contents):
                if contents is None:
                    path.unlink()
                else:
                    path.write_bytes(contents)
                errors = MODULE.validate(self.root)
                self.assertTrue(any(expected in error for error in errors), errors)
                path.write_bytes(original)

    def test_invalid_and_unresolvable_schemas_return_errors_without_network(self):
        path = self.root / f"{MODULE.SKILL}/assets/technique-registry.schema.json"
        original = path.read_bytes()
        for schema, expected in (
            ({"type": "not-a-type"}, "invalid schema"),
            ({"$ref": "#/missing"}, "unresolvable schema reference"),
            ({"$ref": "https://example.invalid/remote.json"}, "local fragment references only"),
        ):
            with self.subTest(schema=schema):
                path.write_text(json.dumps(schema), encoding="utf-8")
                errors = MODULE.validate(self.root)
                self.assertTrue(any(expected in error for error in errors), errors)
                path.write_bytes(original)

    def test_non_mapping_comparator_and_bad_yaml_return_errors(self):
        path = self.root / "evals/comparators/mi_informed.yaml"
        original = path.read_bytes()
        for contents, expected in (("- a list\n", "must be a mapping"), ("field: [\n", "invalid YAML")):
            with self.subTest(contents=contents):
                path.write_text(contents, encoding="utf-8")
                errors = MODULE.validate(self.root)
                self.assertTrue(any(expected in error for error in errors), errors)
                path.write_bytes(original)

    def test_comparators_preserve_identity_status_context_and_read_only_parity(self):
        for name in MODULE.COMPARATORS:
            path = self.root / f"evals/comparators/{name}.yaml"
            original = path.read_bytes()
            for field, value in (
                ("comparator_id", "different_arm"),
                ("status", "qualified"),
                ("same_model_required", False),
                ("same_safety_policy_required", False),
                ("same_context_access_required", False),
                ("memory_policy", "DISABLED"),
                ("instructions", "not a list"),
                ("claim_limit", ""),
            ):
                with self.subTest(name=name, field=field):
                    data = yaml.safe_load(original)
                    data[field] = value
                    path.write_text(yaml.safe_dump(data), encoding="utf-8")
                    errors = MODULE.validate(self.root)
                    self.assertTrue(any(name in error and field in error for error in errors), errors)
                    path.write_bytes(original)

    def test_evidence_references_and_identity_are_checked(self):
        self.assert_rejected(REGISTRY, lambda data: data["ontology"].update(evidence_source_id="missing"), "ontology references")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(evidence_source_ids=["missing"]), "unknown evidence IDs")
        self.assert_rejected(EVIDENCE, lambda data: data["sources"][0].update(conflicts_with=["missing"]), "conflicts with unknown")
        self.assert_rejected(EVIDENCE, lambda data: data["sources"].append(data["sources"][0]), "combined evidence source IDs must be unique")
        canonical = self.root / "provenance/evidence-sources.json"
        canonical.write_text('{"sources":[null]}', encoding="utf-8")
        self.assertIn("canonical evidence sources", "\n".join(MODULE.validate(self.root)))

    def test_legacy_duplicate_comparator_is_rejected(self):
        path = self.root / "evals/baselines/strong_generalist.yaml"
        path.parent.mkdir(parents=True)
        shutil.copyfile(self.root / "evals/comparators/strong_generalist.yaml", path)
        self.assertIn("duplicate legacy baseline", "\n".join(MODULE.validate(self.root)))

    def test_ontology_research_source_does_not_admit_technique_citations(self):
        registry = json.loads((self.root / REGISTRY).read_text(encoding="utf-8"))
        candidate_id = registry["ontology"]["evidence_source_id"]
        self.assertEqual(MODULE.validate(self.root), [])
        self.assert_rejected(
            REGISTRY,
            lambda data: data["techniques"][0]["evidence_source_ids"].append(candidate_id),
            "canonical runtime citations",
        )

    def test_technique_citations_require_both_canonical_and_runtime_admission(self):
        candidate_id = "bcto-2023-ontology"
        with self.changed_json(REGISTRY, lambda data: data["techniques"][0]["evidence_source_ids"].append(candidate_id)):
            with self.changed_json(MODULE.RUNTIME_EVIDENCE_INDEX, lambda data: data["source_ids"].append(candidate_id)):
                self.assertIn("canonical runtime citations", "\n".join(MODULE.validate(self.root)))
            supplement = json.loads((self.root / EVIDENCE).read_text(encoding="utf-8"))
            source = next(item for item in supplement["sources"] if item["id"] == candidate_id)
            with self.changed_json(EVIDENCE, lambda data: data["sources"].remove(source)):
                with self.changed_json("provenance/evidence-sources.json", lambda data: data["sources"].append(source)):
                    errors = MODULE.validate(self.root)
                    self.assertIn("absent from the runtime evidence index", "\n".join(errors))
                    self.assertFalse(any("must be unique" in error for error in errors), errors)

    def test_runtime_evidence_index_shape_errors_are_reported(self):
        self.assert_rejected(
            MODULE.RUNTIME_EVIDENCE_INDEX,
            lambda data: data.update(source_ids=[{}]),
            "runtime evidence-source index must contain a list of source IDs",
        )

    def test_technique_references_and_identities_are_checked(self):
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(alternatives=["PGC-BCT-999"]), "unknown alternatives")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(alternatives=[data["techniques"][0]["id"]]), "itself as an alternative")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][1].update(id=data["techniques"][0]["id"]), "technique IDs must be unique")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][1].update(bcio_id=data["techniques"][0]["bcio_id"]), "BCIO mappings must be unique")

    def test_techniques_cannot_claim_efficacy_or_omit_user_choice(self):
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(efficacy_claim="proven"), "efficacy_claim")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(requires_user_choice=False), "requires_user_choice")
        self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(disconfirming_signal=""), "disconfirming_signal")

    def test_review_window_requires_a_count_or_named_event(self):
        for value in ({"kind": "days", "value": "soon"}, {"kind": "attempts", "value": "tomorrow"}, {"kind": "event", "value": 2}):
            with self.subTest(value=value):
                self.assert_rejected(REGISTRY, lambda data: data["techniques"][0].update(review_window=value), "review_window")

    def test_valid_host_confirmation_is_still_forbidden_in_example(self):
        self.assert_rejected(CAPSULE, lambda data: data["persistence"].update(status="confirmed_by_host", host_receipt_sha256="a" * 64), "example capsule must not claim persistence")

    def test_case_comparator_references_and_status_are_checked(self):
        self.assert_rejected(CASES, lambda data: data["cases"][0].update(required_comparators=["target", "unknown"]), "required_comparators")
        self.assert_rejected(CASES, lambda data: data["cases"][0].update(required_comparators=["strong_generalist", "direct_assistant", "structured_reflection"]), "must include target")
        self.assert_rejected(CASES, lambda data: data.update(status="qualified"), "status")
        with self.changed_json(CASES, lambda data: data["cases"][0]["required_comparators"].append("minimal_visible_model")):
            self.assertEqual(MODULE.validate(self.root), [])

    def test_case_identity_delayed_coverage_and_language_are_checked(self):
        self.assert_rejected(CASES, lambda data: data["cases"][1].update(id=data["cases"][0]["id"]), "case IDs must be unique")
        self.assert_rejected(CASES, lambda data: [case.update(language="en") for case in data["cases"]], "at least two Chinese")
        def odd_suite_with_less_than_half_delayed(data):
            data["cases"].pop()
            for index, case in enumerate(data["cases"]):
                case["delayed_review"]["required"] = index < 6
        self.assert_rejected(CASES, odd_suite_with_less_than_half_delayed, "at least half")

    def test_restricted_community_donors_stay_architecture_only(self):
        for prefix in ("AGPL", "Mixed:"):
            with self.subTest(prefix=prefix):
                def change(data):
                    source = next(item for item in data["sources"] if item["license"].startswith(prefix))
                    source["disposition"] = "ADOPT_TOOLING"
                self.assert_rejected(COMMUNITY, change, "must remain architecture-only")
        self.assert_rejected(COMMUNITY, lambda data: data["sources"].append(data["sources"][0]), "repositories must be unique")

    def test_root_argument_never_changes_default_root(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(MODULE.validate(Path(directory)))
        self.assertEqual(MODULE.ROOT, ROOT)
        self.assertEqual(MODULE.validate(), [])

    def test_cli_reports_invalid_root_as_json_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/validate_design_assets.py"), "--root", directory], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["errors"])

    def test_qualification_preserves_existing_checks_and_adds_design_check(self):
        specification = importlib.util.spec_from_file_location("qualification", ROOT / "scripts/run_deterministic_qualification.py")
        assert specification and specification.loader
        qualification = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(qualification)
        self.assertEqual([check_id for check_id, _ in qualification.CHECKS], [
            "repository-validation", "evaluation-manifest-lint", "learning-pack-validation",
            "multiturn-harness-conformance", "dependency-consistency", "deterministic-unit-tests",
            "growth-record-example", "skill-structure-validation", "design-asset-validation",
        ])
        self.assertEqual(qualification.CHECKS[-1][1], ("scripts/validate_design_assets.py",))


if __name__ == "__main__":
    unittest.main()
