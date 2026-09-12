from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import system_profiles  # noqa: E402


class SystemContractTests(unittest.TestCase):
    def test_contract_order_roles_policies_and_hash_coverage_are_exact(self) -> None:
        expected_ids = tuple(item[0] for item in system_profiles.EXPECTED_SYSTEM_CONTRACT)
        self.assertEqual(system_profiles.SYSTEM_IDS, expected_ids)
        self.assertEqual(set(system_profiles.profile_sha256()), set(expected_ids))
        self.assertEqual(set(system_profiles.profile_bundle_sha256()), set(expected_ids))
        self.assertEqual(
            system_profiles.WRITE_DISABLED_SYSTEMS,
            set(expected_ids) - {"target"},
        )

    def test_reordered_or_semantically_changed_contract_fails_closed(self) -> None:
        original = json.loads(system_profiles.CONTRACT_PATH.read_text(encoding="utf-8"))
        mutations = []

        reordered = copy.deepcopy(original)
        reordered["systems"][1], reordered["systems"][2] = (
            reordered["systems"][2],
            reordered["systems"][1],
        )
        mutations.append(reordered)

        changed_role = copy.deepcopy(original)
        changed_role["systems"][3]["role"] = "renamed_comparator"
        mutations.append(changed_role)

        weakened_policy = copy.deepcopy(original)
        weakened_policy["systems"][4]["context_policy"] = "CONVERSATION_ONLY"
        mutations.append(weakened_policy)

        with tempfile.TemporaryDirectory() as directory_name:
            contract_path = Path(directory_name) / "system-contract.json"
            for mutation in mutations:
                contract_path.write_text(
                    json.dumps(mutation, ensure_ascii=False), encoding="utf-8"
                )
                with mock.patch.object(system_profiles, "CONTRACT_PATH", contract_path):
                    with self.assertRaises(system_profiles.SystemContractError):
                        system_profiles.load_contract()


if __name__ == "__main__":
    unittest.main()
