from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "learning_feasibility_runtime", ROOT / "scripts/learning_feasibility.py"
)
learning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(learning)


class LearningFeasibilityTests(unittest.TestCase):
    def fixture(self, directory: Path):
        identity = directory / "identity.evidence"
        independence = directory / "independence.evidence"
        consent = directory / "consent.evidence"
        reviewer_two_identity = directory / "reviewer-2-identity.evidence"
        reviewer_two_independence = directory / "reviewer-2-independence.evidence"
        reviewer_three_identity = directory / "reviewer-3-identity.evidence"
        reviewer_three_independence = directory / "reviewer-3-independence.evidence"
        for path, text in (
            (identity, "identity"),
            (independence, "independence"),
            (consent, "consent"),
            (reviewer_two_identity, "reviewer two identity"),
            (reviewer_two_independence, "reviewer two independence"),
            (reviewer_three_identity, "reviewer three identity"),
            (reviewer_three_independence, "reviewer three independence"),
        ):
            path.write_text(text, encoding="utf-8")
        candidate = "a" * 40
        topic_hash = learning.file_hash(learning.TOPIC)
        review = {
            "schema_version": "1.0",
            "evidence_class": "learning-content-independent-review",
            "qualification_claim_allowed": False,
            "candidate_commit": candidate,
            "topic_sha256": topic_hash,
            "reviewer_id": "reviewer-0000000000000001",
            "identity_evidence_path": identity.name,
            "identity_evidence_sha256": learning.file_hash(identity),
            "independence_evidence_path": independence.name,
            "independence_evidence_sha256": learning.file_hash(independence),
            "reviewed_at": "2026-09-11T00:00:00Z",
            "source_accuracy_passed": True,
            "answer_key_passed": True,
            "rubric_alignment_passed": True,
            "known_issues": [],
        }
        review["review_sha256"] = learning.digest(review)
        review_path = directory / "content-review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        task_shapes = (
            ("baseline", "baseline"),
            ("player", "immediate"),
            ("player", "seven_day"),
            ("source_reading", "immediate"),
            ("source_reading", "seven_day"),
        )
        participants = []
        task_counter = 1
        for participant_index in range(1, 7):
            tasks = []
            for condition, timepoint in task_shapes:
                artifact = directory / f"artifact-{task_counter}.txt"
                artifact.write_text(
                    f"invented response {task_counter}", encoding="utf-8"
                )
                tasks.append(
                    {
                        "task_id": f"task-{task_counter:016x}",
                        "condition": condition,
                        "timepoint": timepoint,
                        "status": "OBSERVED",
                        "completed_at": (
                            "2026-09-10T23:00:00Z"
                            if timepoint == "baseline"
                            else "2026-09-11T01:00:00Z"
                            if timepoint == "immediate"
                            else "2026-09-18T01:00:00Z"
                        ),
                        "duration_seconds": 300 + task_counter,
                        "help_used": condition == "player" and timepoint == "immediate",
                        "artifact_path": artifact.name,
                        "artifact_sha256": learning.file_hash(artifact),
                        "reviews": [
                            {
                                "reviewer_id": "reviewer-0000000000000002",
                                "condition_blinded": True,
                                "submitted_at": "2026-09-11T01:00:00Z",
                                "scores": {
                                    "responsible_product": 2,
                                    "single_obligation": 2,
                                    "acceptance_boundary": 1,
                                    "verification_evidence": 1,
                                },
                            },
                            {
                                "reviewer_id": "reviewer-0000000000000003",
                                "condition_blinded": True,
                                "submitted_at": "2026-09-11T01:01:00Z",
                                "scores": {
                                    "responsible_product": 2,
                                    "single_obligation": 1,
                                    "acceptance_boundary": 1,
                                    "verification_evidence": 1,
                                },
                            },
                        ],
                    }
                )
                task_counter += 1
            participants.append(
                {
                    "participant_id": f"learner-{participant_index:016x}",
                    "prior_experience": "limited",
                    "sequence": "player_first"
                    if participant_index % 2
                    else "source_reading_first",
                    "session_completed_at": "2026-09-11T00:00:00Z",
                    "consent_evidence_path": consent.name,
                    "consent_evidence_sha256": learning.file_hash(consent),
                    "withdrawn": False,
                    "tasks": tasks,
                }
            )
        document = {
            "schema_version": "1.0",
            "evidence_class": "learning-feasibility-observations",
            "qualification_claim_allowed": False,
            "candidate_commit": candidate,
            "topic_sha256": topic_hash,
            "protocol_sha256": learning.file_hash(learning.PROTOCOL),
            "content_review_path": review_path.name,
            "content_review_sha256": learning.file_hash(review_path),
            "generated_at": "2026-09-11T02:00:00Z",
            "reviewers": [
                {
                    "reviewer_id": "reviewer-0000000000000002",
                    "identity_evidence_path": reviewer_two_identity.name,
                    "identity_evidence_sha256": learning.file_hash(
                        reviewer_two_identity
                    ),
                    "independence_evidence_path": reviewer_two_independence.name,
                    "independence_evidence_sha256": learning.file_hash(
                        reviewer_two_independence
                    ),
                },
                {
                    "reviewer_id": "reviewer-0000000000000003",
                    "identity_evidence_path": reviewer_three_identity.name,
                    "identity_evidence_sha256": learning.file_hash(
                        reviewer_three_identity
                    ),
                    "independence_evidence_path": reviewer_three_independence.name,
                    "independence_evidence_sha256": learning.file_hash(
                        reviewer_three_independence
                    ),
                },
            ],
            "participants": participants,
        }
        source = directory / "observations.json"
        source.write_text(json.dumps(document), encoding="utf-8")
        return source, document

    def test_analysis_requires_independent_content_review_and_two_blinded_scores(self):
        with tempfile.TemporaryDirectory() as directory_name:
            source, document = self.fixture(Path(directory_name))
            self.assertEqual(learning.validate_observations(document, source), [])
            result = learning.analyze(document, source)
            self.assertFalse(result["qualification_claim_allowed"])
            self.assertEqual(result["participant_count"], 6)
            self.assertEqual(result["withdrawal_count"], 0)
            player = next(
                item
                for item in result["condition_timepoint_summaries"]
                if item["condition"] == "player"
                and item["timepoint"] == "seven_day"
            )
            self.assertEqual(player["denominator"], 6)
            self.assertEqual(player["observed_count"], 6)
            self.assertEqual(player["mean_primary_score"], 5.5)

    def test_missingness_remains_visible_and_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source, document = self.fixture(directory)
            missing = copy.deepcopy(document)
            task = missing["participants"][0]["tasks"][-1]
            task.update(
                {
                    "status": "MISSING",
                    "completed_at": None,
                    "duration_seconds": None,
                    "help_used": None,
                    "artifact_path": None,
                    "artifact_sha256": None,
                    "reviews": [],
                }
            )
            self.assertEqual(learning.validate_observations(missing, source), [])
            result = learning.analyze(missing, source)
            delayed = next(
                item
                for item in result["condition_timepoint_summaries"]
                if item["condition"] == "source_reading"
                and item["timepoint"] == "seven_day"
            )
            self.assertEqual(delayed["denominator"], 6)
            self.assertEqual(delayed["missing_or_withdrawn_count"], 1)

            tampered = copy.deepcopy(document)
            tampered["participants"][0]["tasks"][0]["artifact_sha256"] = "0" * 64
            self.assertTrue(
                any(
                    "hash mismatch" in error
                    for error in learning.validate_observations(tampered, source)
                )
            )

            late = copy.deepcopy(document)
            late_task = next(
                task
                for task in late["participants"][0]["tasks"]
                if task["timepoint"] == "seven_day"
            )
            late_task["completed_at"] = "2026-09-12T01:00:00Z"
            self.assertTrue(
                any(
                    "six-to-ten-day" in error
                    for error in learning.validate_observations(late, source)
                )
            )

            bad_review = json.loads(
                (directory / document["content_review_path"]).read_text(
                    encoding="utf-8"
                )
            )
            bad_review["answer_key_passed"] = False
            bad_review["review_sha256"] = learning.digest(
                {key: value for key, value in bad_review.items() if key != "review_sha256"}
            )
            (directory / document["content_review_path"]).write_text(
                json.dumps(bad_review), encoding="utf-8"
            )
            document["content_review_sha256"] = learning.file_hash(
                directory / document["content_review_path"]
            )
            self.assertTrue(
                any(
                    "not passing" in error
                    for error in learning.validate_observations(document, source)
                )
            )


if __name__ == "__main__":
    unittest.main()
