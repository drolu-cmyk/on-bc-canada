"""Pseudonymous learner progress and evidence records for reviewed learning paths."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.control_plane import EventLedger
from runtime.learning_graph import LearningGraphStore


_INSTANCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$")
_SUBMISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$")
_UNIT_STATUSES = {"locked", "available", "in_progress", "completed"}
_SUBMISSION_STATUSES = {
    "submitted",
    "assessment_in_progress",
    "learner_action_required",
    "evidence_not_ready",
    "human_review",
    "accepted",
    "rejected",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class LearnerProgressStore:
    """Freeze reviewed path versions and record learner work without direct identifiers."""

    def __init__(self, path: str | Path, *, program_id: str = "applied-ai-training-canada") -> None:
        self.path = Path(path)
        self.program_id = program_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS learner_path_instances (
                    instance_id TEXT PRIMARY KEY,
                    learner_ref TEXT NOT NULL,
                    cohort_id TEXT NOT NULL,
                    pathway_id TEXT NOT NULL,
                    learning_version TEXT NOT NULL,
                    path_snapshot_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(learner_ref, cohort_id, pathway_id)
                );

                CREATE TABLE IF NOT EXISTS learner_unit_progress (
                    instance_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completion_evidence_refs_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(instance_id, unit_id),
                    FOREIGN KEY(instance_id) REFERENCES learner_path_instances(instance_id)
                );

                CREATE TABLE IF NOT EXISTS learner_submissions (
                    submission_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    artifact_refs_json TEXT NOT NULL,
                    artifact_types_json TEXT NOT NULL,
                    revision_ref TEXT,
                    defense_response_ref TEXT,
                    changed_scenario_response_ref TEXT,
                    mission_requirements_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assessment_execution_id TEXT,
                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(instance_id, unit_id) REFERENCES learner_unit_progress(instance_id, unit_id)
                );

                CREATE TABLE IF NOT EXISTS learner_capability_evidence (
                    instance_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    standard_id TEXT NOT NULL,
                    submission_id TEXT NOT NULL,
                    assessment_execution_id TEXT NOT NULL,
                    accepted_by TEXT NOT NULL,
                    note TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    PRIMARY KEY(instance_id, capability_id, standard_id),
                    FOREIGN KEY(instance_id) REFERENCES learner_path_instances(instance_id),
                    FOREIGN KEY(submission_id) REFERENCES learner_submissions(submission_id)
                );

                CREATE TABLE IF NOT EXISTS learner_event_log (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    instance_id TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY(instance_id) REFERENCES learner_path_instances(instance_id)
                );
                """
            )

    def assign_active_path(
        self,
        *,
        learning_store: LearningGraphStore,
        instance_id: str,
        learner_ref: str,
        cohort_id: str,
        pathway_id: str,
    ) -> dict[str, Any]:
        if not _INSTANCE_ID.fullmatch(instance_id):
            raise ValueError("learner path instance ID is invalid")
        if len(learner_ref.strip()) < 8:
            raise ValueError("learner reference must be pseudonymous and at least 8 characters")
        if len(cohort_id.strip()) < 3:
            raise ValueError("cohort ID is required")
        path = learning_store.active_path(pathway_id)
        if path is None:
            raise ValueError(f"no active learning path for pathway: {pathway_id}")
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM learner_path_instances WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            if existing:
                return self.get_instance(instance_id)
            connection.execute(
                """
                INSERT INTO learner_path_instances (
                    instance_id, learner_ref, cohort_id, pathway_id, learning_version,
                    path_snapshot_json, status, assigned_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    instance_id,
                    learner_ref,
                    cohort_id,
                    pathway_id,
                    path["version"],
                    _dumps(path),
                    now,
                    now,
                ),
            )
            for unit in path["units"]:
                status = "available" if not unit["prerequisite_unit_ids"] else "locked"
                connection.execute(
                    """
                    INSERT INTO learner_unit_progress (
                        instance_id, unit_id, kind, status, completion_evidence_refs_json, updated_at
                    ) VALUES (?, ?, ?, ?, '[]', ?)
                    """,
                    (instance_id, unit["unit_id"], unit["kind"], status, now),
                )
        self._append_event(
            instance_id,
            "learner.path_assigned.v1",
            {"pathway_id": pathway_id, "learning_version": path["version"]},
            retention_class="cohort_lifecycle",
        )
        return self.get_instance(instance_id)

    def start_unit(self, instance_id: str, unit_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM learner_unit_progress WHERE instance_id = ? AND unit_id = ?",
                (instance_id, unit_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"learning unit not found for learner instance: {unit_id}")
            if row["status"] == "completed":
                return self.get_unit(instance_id, unit_id)
            if row["status"] not in {"available", "in_progress"}:
                raise ValueError("learning unit prerequisites are not complete")
            connection.execute(
                "UPDATE learner_unit_progress SET status = 'in_progress', updated_at = ? WHERE instance_id = ? AND unit_id = ?",
                (_utc_now(), instance_id, unit_id),
            )
        self._append_event(
            instance_id,
            "learner.unit_started.v1",
            {"unit_id": unit_id},
            retention_class="cohort_lifecycle",
        )
        return self.get_unit(instance_id, unit_id)

    def complete_practice_unit(self, instance_id: str, unit_id: str, *, evidence_refs: tuple[str, ...] = ()) -> dict[str, Any]:
        unit = self.get_unit(instance_id, unit_id)
        if unit["kind"] == "mission":
            raise ValueError("missions complete only after accepted capability evidence")
        if unit["status"] not in {"available", "in_progress"}:
            raise ValueError("practice unit is not available for completion")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE learner_unit_progress
                SET status = 'completed', completion_evidence_refs_json = ?, updated_at = ?
                WHERE instance_id = ? AND unit_id = ?
                """,
                (_dumps(list(evidence_refs)), _utc_now(), instance_id, unit_id),
            )
        self._unlock_ready_units(instance_id)
        self._append_event(
            instance_id,
            "learner.practice_completed.v1",
            {"unit_id": unit_id, "evidence_ref_count": len(evidence_refs)},
            retention_class="cohort_lifecycle",
        )
        return self.get_unit(instance_id, unit_id)

    def record_mission_submission(
        self,
        *,
        submission_id: str,
        instance_id: str,
        unit_id: str,
        artifact_refs: tuple[str, ...],
        artifact_types: tuple[str, ...],
        revision_ref: str | None = None,
        defense_response_ref: str | None = None,
        changed_scenario_response_ref: str | None = None,
    ) -> dict[str, Any]:
        if not _SUBMISSION_ID.fullmatch(submission_id):
            raise ValueError("submission ID is invalid")
        if not artifact_refs or len(artifact_refs) != len(artifact_types):
            raise ValueError("mission submission requires matching artifact references and types")
        instance = self.get_instance(instance_id)
        unit = self.get_unit(instance_id, unit_id)
        if unit["kind"] != "mission":
            raise ValueError("capability-evidence submission is only valid for a mission")
        if unit["status"] not in {"available", "in_progress"}:
            raise ValueError("mission is not available for submission")
        mission = next(item for item in instance["path_snapshot"]["units"] if item["unit_id"] == unit_id)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM learner_submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
            if existing:
                return self.get_submission(submission_id)
            attempt = connection.execute(
                "SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt FROM learner_submissions WHERE instance_id = ? AND unit_id = ?",
                (instance_id, unit_id),
            ).fetchone()["next_attempt"]
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO learner_submissions (
                    submission_id, instance_id, unit_id, attempt_number,
                    artifact_refs_json, artifact_types_json, revision_ref,
                    defense_response_ref, changed_scenario_response_ref,
                    mission_requirements_json, status, submitted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
                """,
                (
                    submission_id,
                    instance_id,
                    unit_id,
                    attempt,
                    _dumps(list(artifact_refs)),
                    _dumps(list(artifact_types)),
                    revision_ref,
                    defense_response_ref,
                    changed_scenario_response_ref,
                    _dumps(mission["evidence_requirements"]),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE learner_unit_progress SET status = 'in_progress', updated_at = ? WHERE instance_id = ? AND unit_id = ?",
                (now, instance_id, unit_id),
            )
        self._append_event(
            instance_id,
            "learner.mission_submitted.v1",
            {"submission_id": submission_id, "unit_id": unit_id, "attempt_number": attempt},
            retention_class="quality_record",
        )
        return self.get_submission(submission_id)

    def set_submission_assessment_state(
        self,
        submission_id: str,
        *,
        status: str,
        assessment_execution_id: str,
    ) -> dict[str, Any]:
        if status not in _SUBMISSION_STATUSES - {"accepted", "rejected"}:
            raise ValueError(f"unsupported assessment state: {status}")
        submission = self.get_submission(submission_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE learner_submissions
                SET status = ?, assessment_execution_id = ?, updated_at = ?
                WHERE submission_id = ?
                """,
                (status, assessment_execution_id, _utc_now(), submission_id),
            )
        self._append_event(
            submission["instance_id"],
            "learner.assessment_state_changed.v1",
            {"submission_id": submission_id, "status": status, "assessment_execution_id": assessment_execution_id},
            retention_class="quality_record",
        )
        return self.get_submission(submission_id)

    def accept_mission_evidence(
        self,
        submission_id: str,
        *,
        assessment_execution_id: str,
        accepted_by: str,
        note: str,
    ) -> dict[str, Any]:
        if not accepted_by.strip():
            raise ValueError("accepted capability evidence requires an accountable human")
        submission = self.get_submission(submission_id)
        if submission["status"] != "human_review":
            raise ValueError("submission must be at human review before evidence acceptance")
        now = _utc_now()
        with self._connect() as connection:
            for requirement in submission["mission_requirements"]:
                connection.execute(
                    """
                    INSERT INTO learner_capability_evidence (
                        instance_id, capability_id, standard_id, submission_id,
                        assessment_execution_id, accepted_by, note, accepted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instance_id, capability_id, standard_id) DO UPDATE SET
                        submission_id=excluded.submission_id,
                        assessment_execution_id=excluded.assessment_execution_id,
                        accepted_by=excluded.accepted_by,
                        note=excluded.note,
                        accepted_at=excluded.accepted_at
                    """,
                    (
                        submission["instance_id"],
                        requirement["capability_id"],
                        requirement["standard_id"],
                        submission_id,
                        assessment_execution_id,
                        accepted_by,
                        note,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE learner_submissions SET status = 'accepted', assessment_execution_id = ?, updated_at = ? WHERE submission_id = ?",
                (assessment_execution_id, now, submission_id),
            )
            connection.execute(
                "UPDATE learner_unit_progress SET status = 'completed', updated_at = ? WHERE instance_id = ? AND unit_id = ?",
                (now, submission["instance_id"], submission["unit_id"]),
            )
        self._unlock_ready_units(submission["instance_id"])
        self._complete_instance_if_ready(submission["instance_id"])
        self._append_event(
            submission["instance_id"],
            "learner.capability_evidence_accepted.v1",
            {
                "submission_id": submission_id,
                "assessment_execution_id": assessment_execution_id,
                "capability_count": len(submission["mission_requirements"]),
            },
            retention_class="quality_record",
        )
        return self.get_submission(submission_id)

    def reject_mission_evidence(
        self,
        submission_id: str,
        *,
        assessment_execution_id: str,
        rejected_by: str,
        note: str,
    ) -> dict[str, Any]:
        if not rejected_by.strip() or not note.strip():
            raise ValueError("rejection requires an accountable human and reason")
        submission = self.get_submission(submission_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE learner_submissions SET status = 'rejected', assessment_execution_id = ?, updated_at = ? WHERE submission_id = ?",
                (assessment_execution_id, _utc_now(), submission_id),
            )
        self._append_event(
            submission["instance_id"],
            "learner.capability_evidence_rejected.v1",
            {"submission_id": submission_id, "assessment_execution_id": assessment_execution_id, "reason": note},
            retention_class="quality_record",
        )
        return self.get_submission(submission_id)

    def get_instance(self, instance_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learner_path_instances WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"learner path instance not found: {instance_id}")
            units = connection.execute(
                "SELECT * FROM learner_unit_progress WHERE instance_id = ? ORDER BY unit_id",
                (instance_id,),
            ).fetchall()
        return {
            **dict(row),
            "path_snapshot": json.loads(row["path_snapshot_json"]),
            "units": [
                {
                    **dict(item),
                    "completion_evidence_refs": json.loads(item["completion_evidence_refs_json"]),
                }
                for item in units
            ],
        }

    def get_unit(self, instance_id: str, unit_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learner_unit_progress WHERE instance_id = ? AND unit_id = ?",
                (instance_id, unit_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"learning unit not found for learner instance: {unit_id}")
        return {**dict(row), "completion_evidence_refs": json.loads(row["completion_evidence_refs_json"])}

    def get_submission(self, submission_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learner_submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"learner submission not found: {submission_id}")
        return {
            **dict(row),
            "artifact_refs": json.loads(row["artifact_refs_json"]),
            "artifact_types": json.loads(row["artifact_types_json"]),
            "mission_requirements": json.loads(row["mission_requirements_json"]),
        }

    def accepted_capability_evidence(self, instance_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM learner_capability_evidence WHERE instance_id = ? ORDER BY capability_id, standard_id",
                (instance_id,),
            ).fetchall()
        return [dict(item) for item in rows]

    def events(self, instance_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM learner_event_log WHERE instance_id = ? ORDER BY sequence",
                (instance_id,),
            ).fetchall()
        return [json.loads(item["event_json"]) for item in rows]

    def _unlock_ready_units(self, instance_id: str) -> None:
        instance = self.get_instance(instance_id)
        progress = {item["unit_id"]: item["status"] for item in instance["units"]}
        now = _utc_now()
        with self._connect() as connection:
            for unit in instance["path_snapshot"]["units"]:
                if progress[unit["unit_id"]] != "locked":
                    continue
                if all(progress.get(prerequisite_id) == "completed" for prerequisite_id in unit["prerequisite_unit_ids"]):
                    connection.execute(
                        "UPDATE learner_unit_progress SET status = 'available', updated_at = ? WHERE instance_id = ? AND unit_id = ?",
                        (now, instance_id, unit["unit_id"]),
                    )

    def _complete_instance_if_ready(self, instance_id: str) -> None:
        instance = self.get_instance(instance_id)
        if all(unit["status"] == "completed" for unit in instance["units"]):
            with self._connect() as connection:
                connection.execute(
                    "UPDATE learner_path_instances SET status = 'completed', updated_at = ? WHERE instance_id = ?",
                    (_utc_now(), instance_id),
                )
            self._append_event(
                instance_id,
                "learner.path_completed.v1",
                {"pathway_id": instance["pathway_id"], "learning_version": instance["learning_version"]},
                retention_class="cohort_lifecycle",
            )

    def _append_event(self, instance_id: str, event_type: str, payload: dict[str, Any], *, retention_class: str) -> None:
        instance = self.get_instance(instance_id)
        existing = self.events(instance_id)
        ledger = EventLedger(
            events=existing,
            idempotency_keys={event["idempotency_key"]: event["event_id"] for event in existing},
        )
        event = ledger.append(
            event_type=event_type,
            program_id=self.program_id,
            producer="learner-progress-store",
            actor_id="learner-progress-store",
            correlation_id=f"learner-{instance_id}",
            idempotency_key=f"learner:{instance_id}:{event_type}:{len(existing) + 1}",
            payload=payload,
            learner_id=instance["learner_ref"],
            cohort_id=instance["cohort_id"],
            privacy_class="learner_private",
            retention_class=retention_class,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO learner_event_log (instance_id, event_id, event_json) VALUES (?, ?, ?)",
                (instance_id, event["event_id"], _dumps(event)),
            )
