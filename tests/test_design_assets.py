from __future__ import annotations
import copy, importlib.util, json, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("validate_design_assets",ROOT/"scripts/validate_design_assets.py")
assert SPEC and SPEC.loader
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)
class DesignAssetsTests(unittest.TestCase):
    def test_design_assets_validate(self): self.assertEqual(MODULE.validate(ROOT),[])
    def test_techniques_are_falsifiable_and_user_chosen(self):
        registry=json.loads((ROOT/"skill/personal-growth-copilot/assets/technique-registry.json").read_text(encoding="utf-8"))
        for technique in registry["techniques"]:
            self.assertTrue(technique["eligibility_conditions"]); self.assertTrue(technique["contraindications"])
            self.assertTrue(technique["expected_proximal_signal"]); self.assertTrue(technique["disconfirming_signal"])
            self.assertTrue(technique["requires_user_choice"]); self.assertEqual(technique["efficacy_claim"],"not_established_for_this_product")
    def test_capsule_does_not_claim_a_write(self):
        capsule=json.loads((ROOT/"examples/session-capsule.example.json").read_text(encoding="utf-8"))
        self.assertFalse(capsule["retention"]["stored"]); self.assertIsNone(capsule["retention"]["host_receipt"])
        self.assertNotEqual(capsule["memory_delta"]["status"],"COMMITTED")

    def test_capsule_receipt_matches_storage_state(self):
        schema=json.loads((ROOT/"skill/personal-growth-copilot/assets/session-capsule.schema.json").read_text(encoding="utf-8"))
        capsule=json.loads((ROOT/"examples/session-capsule.example.json").read_text(encoding="utf-8"))
        validator=Draft202012Validator(schema)
        with_receipt=copy.deepcopy(capsule)
        with_receipt["retention"]["host_receipt"]="unverified-receipt"
        self.assertTrue(list(validator.iter_errors(with_receipt)))
        without_receipt=copy.deepcopy(capsule)
        without_receipt["retention"]["stored"]=True
        self.assertTrue(list(validator.iter_errors(without_receipt)))
    def test_ordinary_suite_contains_delayed_and_chinese_cases(self):
        cases=json.loads((ROOT/"evals/ordinary-growth-cases.json").read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases),12)
        self.assertGreaterEqual(sum(case["delayed_review"]["required"] for case in cases),len(cases)//2)
        self.assertGreaterEqual(sum(case["language"] in {"zh","mixed"} for case in cases),2)
if __name__=="__main__": unittest.main()
