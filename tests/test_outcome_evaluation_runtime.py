from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "outcome_evaluation_runtime", ROOT / "scripts/outcome_evaluation.py"
)
outcomes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outcomes)


class OutcomeEvaluationRuntimeTests(unittest.TestCase):
    def make_document(self, directory: Path):
        design = json.loads(
            (ROOT / "evals/outcome-measures.json").read_text(encoding="utf-8")
        )
        roster = [
            {
                "episode_id": "episode-0000000000000001",
                "system_id": "target",
                "participant_state": "COMPLETED",
            },
            {
                "episode_id": "episode-0000000000000002",
                "system_id": "target",
                "participant_state": "DROPOUT",
            },
        ]
        observations = []
        counter = 1
        for episode in roster:
            for measure in design["measures"]:
                for point in measure["collection_points"]:
                    observed = episode["participant_state"] == "COMPLETED"
                    status = "OBSERVED" if observed else "MISSING"
                    value = None
                    evidence_path = None
                    evidence_sha256 = None
                    observed_at = None
                    if observed:
                        if measure["id"] == "user_confirmed_decision_state_improved":
                            value = "clearer_choice"
                        elif measure["id"] == "review_point_learning_completed":
                            value = "observation_recorded_model_updated"
                        elif measure["value_type"] == "boolean":
                            value = False if measure["id"] == "human_support_displacement" else True
                        elif measure["value_type"] in {"ordinal", "categorical"}:
                            value = measure["anchors"][0]
                        elif measure["value_type"] == "count":
                            value = 1
                        elif measure["value_type"] == "duration":
                            value = 600.0
                        evidence = directory / f"evidence-{counter}.json"
                        evidence.write_text(
                            json.dumps({"observation": counter}), encoding="utf-8"
                        )
                        evidence_path = evidence.name
                        evidence_sha256 = hashlib.sha256(evidence.read_bytes()).hexdigest()
                        observed_at = "2026-09-11T12:00:00Z"
                    observations.append(
                        {
                            "observation_id": f"obs-{counter:024x}",
                            "episode_id": episode["episode_id"],
                            "system_id": episode["system_id"],
                            "measure_id": measure["id"],
                            "collection_point": point,
                            "status": status,
                            "value": value,
                            "observed_at": observed_at,
                            "evidence_path": evidence_path,
                            "evidence_sha256": evidence_sha256,
                        }
                    )
                    counter += 1
        return {
            "schema_version": "1.0",
            "evidence_class": "product-outcome-observations",
            "qualification_claim_allowed": False,
            "candidate_commit": "a" * 40,
            "design_sha256": outcomes.digest(design),
            "generated_at": "2026-09-11T12:00:00Z",
            "episode_roster": roster,
            "observations": observations,
        }

    def test_exact_observation_schedule_preserves_missingness_and_primary_denominator(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = directory / "observations.json"
            document = self.make_document(directory)
            source.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(
                outcomes.validate_observations(document, source_path=source), []
            )
            result = outcomes.analyze(
                document,
                source_path=source,
                generated_at=datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc),
            )
            self.assertFalse(result["qualification_claim_allowed"])
            self.assertEqual(result["episode_count"], 2)
            self.assertEqual(result["participant_states"]["DROPOUT"], 1)
            primary = next(
                item
                for item in result["measure_summaries"]
                if item["measure_id"] == "user_confirmed_decision_state_improved"
                and item["collection_point"] == "post_session"
            )
            self.assertEqual(primary["denominator"], 2)
            self.assertEqual(primary["status_counts"], {"MISSING": 1, "OBSERVED": 1})
            self.assertEqual(primary["primary_success_count"], 1)
            self.assertEqual(primary["primary_rate_denominator"], 2)
            self.assertEqual(primary["primary_success_rate"], 0.5)

    def test_omission_bad_anchor_and_evidence_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = directory / "observations.json"
            document = self.make_document(directory)
            source.write_text(json.dumps(document), encoding="utf-8")

            missing = copy.deepcopy(document)
            missing["observations"].pop()
            self.assertTrue(
                any(
                    "exact episode/measure schedule" in error
                    for error in outcomes.validate_observations(
                        missing, source_path=source
                    )
                )
            )

            bad_anchor = copy.deepcopy(document)
            item = next(
                value
                for value in bad_anchor["observations"]
                if value["measure_id"] == "user_confirmed_decision_state_improved"
                and value["status"] == "OBSERVED"
            )
            item["value"] = "invented_favorable_anchor"
            self.assertTrue(
                any(
                    "governed type or anchors" in error
                    for error in outcomes.validate_observations(
                        bad_anchor, source_path=source
                    )
                )
            )

            observed = next(
                value for value in document["observations"] if value["status"] == "OBSERVED"
            )
            (directory / observed["evidence_path"]).write_text(
                "tampered", encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "hash mismatch" in error
                    for error in outcomes.validate_observations(
                        document, source_path=source
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
