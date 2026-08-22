from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime.graph_kernel import GraphKernel
from runtime.outcomes_intelligence import OutcomesSnapshotBuilder
from runtime.outcomes_intelligence_graph import OutcomesIntelligenceGraph


class FakeOutcomesProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def analyze_outcomes(self, snapshot):
        self.calls.append("analyse")
        return {
            "status": "material_signal",
            "findings": [
                {
                    "theme": "mission evidence friction",
                    "signal_type": "friction",
                    "evidence_metrics": ["completion.rate", "average_attempt_number"],
                    "interpretation": "The released aggregate warrants investigation, not a curriculum conclusion.",
                    "research_question": "What work-design factors are associated with repeated mission attempts in this pathway?",
                }
            ],
            "limitations": ["Aggregate observation does not establish causation."],
            "summary": "A bounded programme-level signal is present.",
        }

    def challenge_outcomes(self, snapshot, analysis):
        self.calls.append("challenge")
        return {
            "status": "narrows",
            "cautions": ["Do not interpret completion as employment readiness."],
            "surviving_questions": [
                "Does the signal persist after separating path versions and observation windows?"
            ],
            "summary": "The signal survives only as a research question.",
        }


class OutcomesSnapshotTests(unittest.TestCase):
    def _store(self, directory: str, *, learners: int) -> Path:
        path = Path(directory) / "learner.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE learner_path_instances (
                    instance_id TEXT PRIMARY KEY,
                    pathway_id TEXT NOT NULL,
                    learning_version TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE learner_unit_progress (
                    instance_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE learner_submissions (
                    instance_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE learner_capability_evidence (
                    instance_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL
                );
                """
            )
            for index in range(learners):
                instance = f"inst-{index:03d}"
                connection.execute(
                    "INSERT INTO learner_path_instances VALUES (?, 'applied-ai-systems', 'v1', ?)",
                    (instance, "completed" if index < learners // 2 else "active"),
                )
                connection.execute(
                    "INSERT INTO learner_unit_progress VALUES (?, 'sprint', 'completed')",
                    (instance,),
                )
                connection.execute(
                    "INSERT INTO learner_unit_progress VALUES (?, 'mission', ?)",
                    (instance, "completed" if index < learners // 2 else "in_progress"),
                )
                connection.execute(
                    "INSERT INTO learner_submissions VALUES (?, ?, ?)",
                    (instance, 1 + (index % 2), "accepted" if index < learners // 2 else "submitted"),
                )
                if index < learners // 2:
                    connection.execute(
                        "INSERT INTO learner_capability_evidence VALUES (?, 'capability-core')",
                        (instance,),
                    )
                if index < 4:
                    connection.execute(
                        "INSERT INTO learner_capability_evidence VALUES (?, 'capability-rare')",
                        (instance,),
                    )
        return path

    def test_releases_only_privacy_safe_aggregate_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = OutcomesSnapshotBuilder(self._store(directory, learners=20)).build()
        self.assertEqual(1, len(snapshot["groups"]))
        group = snapshot["groups"][0]
        self.assertEqual("released", group["privacy_status"])
        self.assertEqual(0.5, group["completion"]["rate"])
        self.assertEqual(0.5, group["learners_with_accepted_capability_evidence"]["rate"])
        self.assertEqual(["capability-core"], [item["capability_id"] for item in group["capability_evidence_rates"]])
        self.assertEqual(1, group["suppressed_capability_metric_count"])
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("inst-", encoded)
        self.assertNotIn("cohort_id", encoded)
        self.assertNotIn("submission_id", encoded)
        self.assertFalse(snapshot["model_boundary"]["contains_direct_learner_identity"])

    def test_group_below_minimum_population_is_not_released(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = OutcomesSnapshotBuilder(self._store(directory, learners=19)).build()
        self.assertEqual([], snapshot["groups"])
        self.assertEqual(1, snapshot["suppressed_group_count"])
        self.assertEqual("minimum_population", snapshot["suppressed_groups"][0]["reason"])


class OutcomesIntelligenceGraphTests(unittest.TestCase):
    @staticmethod
    def _snapshot():
        return {
            "snapshot_version": "0.1.0",
            "aggregation": "pathway_learning_version",
            "privacy_policy": {"minimum_population": 20, "minimum_binary_cell": 5},
            "groups": [{"pathway_id": "applied-ai-systems", "learning_version": "v1", "learner_count": 20}],
            "suppressed_group_count": 0,
            "model_boundary": {
                "contains_direct_learner_identity": False,
                "contains_cohort_id": False,
                "contains_submission_or_artifact_reference": False,
                "contains_assessor_identity": False,
                "contains_free_text_notes": False,
            },
        }

    def test_material_signal_finishes_as_research_question_not_curriculum_change(self):
        provider = FakeOutcomesProvider()
        graph = OutcomesIntelligenceGraph(GraphKernel(), provider)
        graph.register()
        definition, execution = graph.start(execution_id="outcomes-test-001", snapshot=self._snapshot())
        self.assertEqual("completed", execution.status)
        self.assertEqual(["analyse", "challenge"], provider.calls)
        packet = execution.state["outcomes_packet"]
        self.assertTrue(packet["research_signal"]["requires_independent_research_validation"])
        self.assertEqual("aggregate programme intelligence only", packet["boundary"])
        self.assertNotIn("curriculum_change", packet)
        self.assertEqual("finalize_outcomes", execution.history[-1]["node_id"])
        self.assertEqual("outcomes-intelligence", definition.graph_id)

    def test_learner_level_field_fails_before_agents_run(self):
        provider = FakeOutcomesProvider()
        graph = OutcomesIntelligenceGraph(GraphKernel(), provider)
        graph.register()
        snapshot = self._snapshot()
        snapshot["learner_ref"] = "pseudonymous-but-still-private"
        _, execution = graph.start(execution_id="outcomes-test-002", snapshot=snapshot)
        self.assertEqual("failed", execution.status)
        self.assertIn("prohibited learner-level field", execution.failure)
        self.assertEqual([], provider.calls)


if __name__ == "__main__":
    unittest.main()
