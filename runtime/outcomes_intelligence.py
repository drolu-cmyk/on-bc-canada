"""Privacy-preserving aggregate learner outcomes for programme intelligence.

This module reads the pseudonymous learner progress store but releases only
pathway-and-version aggregates. It never returns learner references, instance IDs,
submission IDs, artifact references, assessor IDs, cohort IDs, or free-text notes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIN_AGGREGATE_POPULATION = 20
MIN_BINARY_CELL = 5


@dataclass(frozen=True)
class OutcomePrivacyPolicy:
    minimum_population: int = MIN_AGGREGATE_POPULATION
    minimum_binary_cell: int = MIN_BINARY_CELL

    def __post_init__(self) -> None:
        if self.minimum_population < 10:
            raise ValueError("outcome minimum population must be at least 10")
        if self.minimum_binary_cell < 3:
            raise ValueError("outcome binary-cell minimum must be at least 3")

    def release_binary_rate(self, positive: int, denominator: int) -> dict[str, Any]:
        negative = denominator - positive
        if denominator < self.minimum_population:
            return {"status": "suppressed", "reason": "minimum_population"}
        if positive < self.minimum_binary_cell or negative < self.minimum_binary_cell:
            return {"status": "suppressed", "reason": "small_binary_cell"}
        return {
            "status": "released",
            "numerator": positive,
            "denominator": denominator,
            "rate": round(positive / denominator, 4),
        }


class OutcomesSnapshotBuilder:
    """Create agent-safe aggregate outcomes from LearnerProgressStore SQLite."""

    def __init__(self, path: str | Path, *, policy: OutcomePrivacyPolicy | None = None) -> None:
        self.path = Path(path)
        self.policy = policy or OutcomePrivacyPolicy()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def build(self, *, pathway_id: str | None = None, learning_version: str | None = None) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"learner progress store not found: {self.path}")
        clauses: list[str] = []
        params: list[str] = []
        if pathway_id:
            clauses.append("pathway_id = ?")
            params.append(pathway_id)
        if learning_version:
            clauses.append("learning_version = ?")
            params.append(learning_version)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""

        with self._connect() as connection:
            groups = connection.execute(
                f"""
                SELECT pathway_id, learning_version, COUNT(*) AS learner_count
                FROM learner_path_instances{where}
                GROUP BY pathway_id, learning_version
                ORDER BY pathway_id, learning_version
                """,
                params,
            ).fetchall()
            snapshots = [self._build_group(connection, row) for row in groups]

        released = [item for item in snapshots if item["privacy_status"] == "released"]
        suppressed = [item for item in snapshots if item["privacy_status"] != "released"]
        return {
            "snapshot_version": "0.1.0",
            "aggregation": "pathway_learning_version",
            "privacy_policy": {
                "minimum_population": self.policy.minimum_population,
                "minimum_binary_cell": self.policy.minimum_binary_cell,
                "cohort_level_release": False,
                "individual_level_release": False,
            },
            "groups": released,
            "suppressed_group_count": len(suppressed),
            "suppressed_groups": [
                {
                    "pathway_id": item["pathway_id"],
                    "learning_version": item["learning_version"],
                    "reason": item["suppression_reason"],
                }
                for item in suppressed
            ],
            "model_boundary": {
                "contains_direct_learner_identity": False,
                "contains_cohort_id": False,
                "contains_submission_or_artifact_reference": False,
                "contains_assessor_identity": False,
                "contains_free_text_notes": False,
            },
        }

    def _build_group(self, connection: sqlite3.Connection, group: sqlite3.Row) -> dict[str, Any]:
        pathway_id = group["pathway_id"]
        version = group["learning_version"]
        learner_count = int(group["learner_count"])
        base = {
            "pathway_id": pathway_id,
            "learning_version": version,
            "learner_count": learner_count,
        }
        if learner_count < self.policy.minimum_population:
            return {
                **base,
                "privacy_status": "suppressed",
                "suppression_reason": "minimum_population",
            }

        params = (pathway_id, version)
        completed = int(
            connection.execute(
                """
                SELECT COUNT(*) AS value FROM learner_path_instances
                WHERE pathway_id = ? AND learning_version = ? AND status = 'completed'
                """,
                params,
            ).fetchone()["value"]
        )
        with_evidence = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT e.instance_id) AS value
                FROM learner_capability_evidence e
                JOIN learner_path_instances i ON i.instance_id = e.instance_id
                WHERE i.pathway_id = ? AND i.learning_version = ?
                """,
                params,
            ).fetchone()["value"]
        )
        submissions = connection.execute(
            """
            SELECT COUNT(*) AS submissions,
                   COUNT(DISTINCT s.instance_id) AS submitting_learners,
                   SUM(CASE WHEN s.status = 'accepted' THEN 1 ELSE 0 END) AS accepted_submissions,
                   AVG(s.attempt_number) AS average_attempt_number
            FROM learner_submissions s
            JOIN learner_path_instances i ON i.instance_id = s.instance_id
            WHERE i.pathway_id = ? AND i.learning_version = ?
            """,
            params,
        ).fetchone()
        unit_counts = connection.execute(
            """
            SELECT p.kind, p.status, COUNT(*) AS value
            FROM learner_unit_progress p
            JOIN learner_path_instances i ON i.instance_id = p.instance_id
            WHERE i.pathway_id = ? AND i.learning_version = ?
            GROUP BY p.kind, p.status
            """,
            params,
        ).fetchall()
        capability_rows = connection.execute(
            """
            SELECT e.capability_id, COUNT(DISTINCT e.instance_id) AS learner_count
            FROM learner_capability_evidence e
            JOIN learner_path_instances i ON i.instance_id = e.instance_id
            WHERE i.pathway_id = ? AND i.learning_version = ?
            GROUP BY e.capability_id
            ORDER BY e.capability_id
            """,
            params,
        ).fetchall()

        capability_metrics: list[dict[str, Any]] = []
        suppressed_capability_count = 0
        for row in capability_rows:
            released = self.policy.release_binary_rate(int(row["learner_count"]), learner_count)
            if released["status"] == "released":
                capability_metrics.append({"capability_id": row["capability_id"], **released})
            else:
                suppressed_capability_count += 1

        return {
            **base,
            "privacy_status": "released",
            "completion": self.policy.release_binary_rate(completed, learner_count),
            "learners_with_accepted_capability_evidence": self.policy.release_binary_rate(with_evidence, learner_count),
            "submission_summary": {
                "submission_count": int(submissions["submissions"] or 0),
                "submitting_learner_count": int(submissions["submitting_learners"] or 0),
                "accepted_submission_count": int(submissions["accepted_submissions"] or 0),
                "average_attempt_number": round(float(submissions["average_attempt_number"]), 2)
                if submissions["average_attempt_number"] is not None
                else None,
            },
            "unit_status_counts": [
                {"kind": row["kind"], "status": row["status"], "count": int(row["value"])}
                for row in unit_counts
            ],
            "capability_evidence_rates": capability_metrics,
            "suppressed_capability_metric_count": suppressed_capability_count,
        }
