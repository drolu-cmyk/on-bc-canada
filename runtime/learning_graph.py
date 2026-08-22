"""Reviewed learning graph built on active learner capabilities.

The Capability Graph defines what must be demonstrated. The Learning Graph maps
those active capabilities to sprints, labs, missions, and evidence requirements.
Agent-authored learning paths remain candidates until deterministic validation and
an accountable human activation decision succeed.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from runtime.capability_graph import CapabilityGraphStore


LearningUnitKind = Literal["sprint", "lab", "mission"]
LearningPathStatus = Literal["candidate", "active", "retired"]

_UNIT_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,99}$")
_ALLOWED_KINDS = {"sprint", "lab", "mission"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class EvidenceRequirement:
    capability_id: str
    standard_id: str

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.standard_id.strip():
            raise ValueError("evidence requirement needs a capability and evidence standard")


@dataclass(frozen=True)
class LearningUnit:
    unit_id: str
    kind: LearningUnitKind
    title: str
    purpose: str
    develops_capability_ids: tuple[str, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    prerequisite_unit_ids: tuple[str, ...] = ()
    source_module_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _UNIT_ID.fullmatch(self.unit_id):
            raise ValueError("learning unit ID must be a stable lowercase identifier")
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported learning unit kind: {self.kind}")
        if len(self.title.strip()) < 3 or len(self.purpose.strip()) < 20:
            raise ValueError("learning unit title and purpose must be specific")
        if not self.develops_capability_ids:
            raise ValueError("learning unit must develop at least one capability")
        if len(set(self.develops_capability_ids)) != len(self.develops_capability_ids):
            raise ValueError("duplicate developed capabilities are not allowed")
        if self.unit_id in self.prerequisite_unit_ids:
            raise ValueError("learning unit cannot require itself")
        if len(set(self.prerequisite_unit_ids)) != len(self.prerequisite_unit_ids):
            raise ValueError("duplicate learning unit prerequisites are not allowed")
        evidence_pairs = [(item.capability_id, item.standard_id) for item in self.evidence_requirements]
        if len(set(evidence_pairs)) != len(evidence_pairs):
            raise ValueError("duplicate evidence requirements are not allowed")
        if self.evidence_requirements and self.kind != "mission":
            raise ValueError("evidence standards for capability verification must be attached to missions")
        undeveloped = {
            item.capability_id for item in self.evidence_requirements
        } - set(self.develops_capability_ids)
        if undeveloped:
            raise ValueError(f"mission cannot assess capabilities it does not develop: {sorted(undeveloped)}")


@dataclass(frozen=True)
class LearningPathDefinition:
    pathway_id: str
    version: str
    title: str
    target_capability_ids: tuple[str, ...]
    units: tuple[LearningUnit, ...]

    def __post_init__(self) -> None:
        if not self.pathway_id.strip() or not self.version.strip():
            raise ValueError("learning path requires pathway ID and version")
        if len(self.title.strip()) < 3:
            raise ValueError("learning path title is required")
        if not self.target_capability_ids:
            raise ValueError("learning path requires at least one target capability")
        if len(set(self.target_capability_ids)) != len(self.target_capability_ids):
            raise ValueError("duplicate target capabilities are not allowed")
        if not self.units:
            raise ValueError("learning path requires at least one learning unit")
        unit_ids = [unit.unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("learning unit IDs must be unique within a path")
        known = set(unit_ids)
        for unit in self.units:
            missing = set(unit.prerequisite_unit_ids) - known
            if missing:
                raise ValueError(f"unknown prerequisite learning units for {unit.unit_id}: {sorted(missing)}")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        prerequisites = {unit.unit_id: set(unit.prerequisite_unit_ids) for unit in self.units}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(unit_id: str) -> None:
            if unit_id in visiting:
                raise ValueError("learning unit prerequisites contain a cycle")
            if unit_id in visited:
                return
            visiting.add(unit_id)
            for prerequisite_id in prerequisites[unit_id]:
                visit(prerequisite_id)
            visiting.remove(unit_id)
            visited.add(unit_id)

        for unit_id in prerequisites:
            visit(unit_id)


class LearningGraphStore:
    """Persist validated learning-path candidates and human activation records."""

    STORE_VERSION = "0.1.0"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
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
                CREATE TABLE IF NOT EXISTS learning_paths (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    store_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version)
                );

                CREATE TABLE IF NOT EXISTS learning_units (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    source_module_ids_json TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version, unit_id),
                    FOREIGN KEY(pathway_id, version) REFERENCES learning_paths(pathway_id, version)
                );

                CREATE TABLE IF NOT EXISTS learning_path_targets (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version, capability_id),
                    FOREIGN KEY(pathway_id, version) REFERENCES learning_paths(pathway_id, version)
                );

                CREATE TABLE IF NOT EXISTS learning_unit_capabilities (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version, unit_id, capability_id, relation_type),
                    FOREIGN KEY(pathway_id, version, unit_id) REFERENCES learning_units(pathway_id, version, unit_id)
                );

                CREATE TABLE IF NOT EXISTS learning_unit_prerequisites (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    prerequisite_unit_id TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version, unit_id, prerequisite_unit_id),
                    FOREIGN KEY(pathway_id, version, unit_id) REFERENCES learning_units(pathway_id, version, unit_id),
                    FOREIGN KEY(pathway_id, version, prerequisite_unit_id) REFERENCES learning_units(pathway_id, version, unit_id)
                );

                CREATE TABLE IF NOT EXISTS learning_unit_evidence (
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    standard_id TEXT NOT NULL,
                    PRIMARY KEY(pathway_id, version, unit_id, capability_id, standard_id),
                    FOREIGN KEY(pathway_id, version, unit_id) REFERENCES learning_units(pathway_id, version, unit_id)
                );

                CREATE TABLE IF NOT EXISTS learning_path_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pathway_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    approver_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    FOREIGN KEY(pathway_id, version) REFERENCES learning_paths(pathway_id, version)
                );
                """
            )

    def save_candidate(self, definition: LearningPathDefinition, *, capabilities: CapabilityGraphStore) -> dict[str, Any]:
        capability_records = self._validate_against_capabilities(definition, capabilities)
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT status FROM learning_paths WHERE pathway_id = ? AND version = ?",
                (definition.pathway_id, definition.version),
            ).fetchone()
            if existing and existing["status"] in {"active", "retired"}:
                raise ValueError("an active or retired learning path version cannot be replaced by an agent candidate")

            connection.execute(
                """
                INSERT INTO learning_paths (
                    pathway_id, version, title, status, store_version, created_at, updated_at
                ) VALUES (?, ?, ?, 'candidate', ?, ?, ?)
                ON CONFLICT(pathway_id, version) DO UPDATE SET
                    title=excluded.title,
                    status='candidate',
                    store_version=excluded.store_version,
                    updated_at=excluded.updated_at
                """,
                (definition.pathway_id, definition.version, definition.title, self.STORE_VERSION, now, now),
            )
            for table in (
                "learning_path_targets",
                "learning_unit_evidence",
                "learning_unit_prerequisites",
                "learning_unit_capabilities",
                "learning_units",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE pathway_id = ? AND version = ?",
                    (definition.pathway_id, definition.version),
                )

            for capability_id in definition.target_capability_ids:
                connection.execute(
                    "INSERT INTO learning_path_targets (pathway_id, version, capability_id) VALUES (?, ?, ?)",
                    (definition.pathway_id, definition.version, capability_id),
                )

            # Write all unit rows before prerequisite edges so input order never
            # changes foreign-key validity.
            for unit in definition.units:
                connection.execute(
                    """
                    INSERT INTO learning_units (
                        pathway_id, version, unit_id, kind, title, purpose, source_module_ids_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.pathway_id,
                        definition.version,
                        unit.unit_id,
                        unit.kind,
                        unit.title,
                        unit.purpose,
                        _dumps(list(unit.source_module_ids)),
                    ),
                )

            for unit in definition.units:
                for capability_id in unit.develops_capability_ids:
                    connection.execute(
                        """
                        INSERT INTO learning_unit_capabilities (
                            pathway_id, version, unit_id, capability_id, relation_type
                        ) VALUES (?, ?, ?, ?, 'develops')
                        """,
                        (definition.pathway_id, definition.version, unit.unit_id, capability_id),
                    )
                for prerequisite_id in unit.prerequisite_unit_ids:
                    connection.execute(
                        """
                        INSERT INTO learning_unit_prerequisites (
                            pathway_id, version, unit_id, prerequisite_unit_id
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (definition.pathway_id, definition.version, unit.unit_id, prerequisite_id),
                    )
                for requirement in unit.evidence_requirements:
                    connection.execute(
                        """
                        INSERT INTO learning_unit_evidence (
                            pathway_id, version, unit_id, capability_id, standard_id
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            definition.pathway_id,
                            definition.version,
                            unit.unit_id,
                            requirement.capability_id,
                            requirement.standard_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO learning_unit_capabilities (
                            pathway_id, version, unit_id, capability_id, relation_type
                        ) VALUES (?, ?, ?, ?, 'assesses')
                        """,
                        (definition.pathway_id, definition.version, unit.unit_id, requirement.capability_id),
                    )
        result = self.get(definition.pathway_id, definition.version)
        result["capability_snapshot"] = {
            capability_id: {
                "status": capability_records[capability_id]["status"],
                "target_level": capability_records[capability_id]["target_level"],
                "source_confidence": capability_records[capability_id]["source_confidence"],
            }
            for capability_id in sorted(capability_records)
        }
        return result

    def _validate_against_capabilities(
        self,
        definition: LearningPathDefinition,
        capabilities: CapabilityGraphStore,
    ) -> dict[str, dict[str, Any]]:
        referenced = set(definition.target_capability_ids)
        for unit in definition.units:
            referenced.update(unit.develops_capability_ids)
            referenced.update(item.capability_id for item in unit.evidence_requirements)

        records: dict[str, dict[str, Any]] = {}
        for capability_id in sorted(referenced):
            record = capabilities.get(capability_id)
            if record["status"] != "active":
                raise ValueError(f"learning path references capability that is not active: {capability_id}")
            records[capability_id] = record

        for target_id in definition.target_capability_ids:
            if records[target_id]["pathway_id"] not in {definition.pathway_id, "common-core"}:
                raise ValueError(f"target capability belongs to another pathway: {target_id}")

        accepted_standards = {
            capability_id: {item["standard_id"] for item in record["evidence_standards"]}
            for capability_id, record in records.items()
        }
        mission_coverage: dict[str, set[str]] = {capability_id: set() for capability_id in definition.target_capability_ids}
        for unit in definition.units:
            for requirement in unit.evidence_requirements:
                if requirement.standard_id not in accepted_standards[requirement.capability_id]:
                    raise ValueError(
                        f"mission {unit.unit_id} references unknown evidence standard "
                        f"{requirement.standard_id} for {requirement.capability_id}"
                    )
                if requirement.capability_id in mission_coverage:
                    mission_coverage[requirement.capability_id].add(requirement.standard_id)

        uncovered = sorted(capability_id for capability_id, standards in mission_coverage.items() if not standards)
        if uncovered:
            raise ValueError(f"target capabilities lack mission evidence coverage: {uncovered}")
        return records

    def activate(self, pathway_id: str, version: str, *, approver_id: str, note: str) -> dict[str, Any]:
        if not approver_id.strip() or not note.strip():
            raise ValueError("learning path activation requires an accountable human and review note")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM learning_paths WHERE pathway_id = ? AND version = ?",
                (pathway_id, version),
            ).fetchone()
            if row is None:
                raise KeyError(f"learning path not found: {pathway_id}@{version}")
            if row["status"] != "candidate":
                raise ValueError("only a candidate learning path can be activated")
            other_active = connection.execute(
                "SELECT version FROM learning_paths WHERE pathway_id = ? AND status = 'active' AND version <> ?",
                (pathway_id, version),
            ).fetchone()
            if other_active:
                raise ValueError(f"retire active learning path version before activation: {other_active['version']}")
            now = _utc_now()
            connection.execute(
                "UPDATE learning_paths SET status = 'active', updated_at = ? WHERE pathway_id = ? AND version = ?",
                (now, pathway_id, version),
            )
            connection.execute(
                """
                INSERT INTO learning_path_decisions (
                    pathway_id, version, decision, approver_id, note, decided_at
                ) VALUES (?, ?, 'activate', ?, ?, ?)
                """,
                (pathway_id, version, approver_id, note, now),
            )
        return self.get(pathway_id, version)

    def retire(self, pathway_id: str, version: str, *, approver_id: str, note: str) -> dict[str, Any]:
        if not approver_id.strip() or not note.strip():
            raise ValueError("learning path retirement requires an accountable human and reason")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM learning_paths WHERE pathway_id = ? AND version = ?",
                (pathway_id, version),
            ).fetchone()
            if row is None:
                raise KeyError(f"learning path not found: {pathway_id}@{version}")
            if row["status"] != "active":
                raise ValueError("only an active learning path can be retired")
            now = _utc_now()
            connection.execute(
                "UPDATE learning_paths SET status = 'retired', updated_at = ? WHERE pathway_id = ? AND version = ?",
                (now, pathway_id, version),
            )
            connection.execute(
                """
                INSERT INTO learning_path_decisions (
                    pathway_id, version, decision, approver_id, note, decided_at
                ) VALUES (?, ?, 'retire', ?, ?, ?)
                """,
                (pathway_id, version, approver_id, note, now),
            )
        return self.get(pathway_id, version)

    def get(self, pathway_id: str, version: str) -> dict[str, Any]:
        with self._connect() as connection:
            path = connection.execute(
                "SELECT * FROM learning_paths WHERE pathway_id = ? AND version = ?",
                (pathway_id, version),
            ).fetchone()
            if path is None:
                raise KeyError(f"learning path not found: {pathway_id}@{version}")
            targets = connection.execute(
                "SELECT capability_id FROM learning_path_targets WHERE pathway_id = ? AND version = ? ORDER BY capability_id",
                (pathway_id, version),
            ).fetchall()
            units = connection.execute(
                "SELECT * FROM learning_units WHERE pathway_id = ? AND version = ? ORDER BY unit_id",
                (pathway_id, version),
            ).fetchall()
            prerequisites = connection.execute(
                "SELECT unit_id, prerequisite_unit_id FROM learning_unit_prerequisites WHERE pathway_id = ? AND version = ? ORDER BY unit_id, prerequisite_unit_id",
                (pathway_id, version),
            ).fetchall()
            capabilities = connection.execute(
                "SELECT unit_id, capability_id, relation_type FROM learning_unit_capabilities WHERE pathway_id = ? AND version = ? ORDER BY unit_id, relation_type, capability_id",
                (pathway_id, version),
            ).fetchall()
            evidence = connection.execute(
                "SELECT unit_id, capability_id, standard_id FROM learning_unit_evidence WHERE pathway_id = ? AND version = ? ORDER BY unit_id, capability_id, standard_id",
                (pathway_id, version),
            ).fetchall()
            decisions = connection.execute(
                "SELECT decision, approver_id, note, decided_at FROM learning_path_decisions WHERE pathway_id = ? AND version = ? ORDER BY decision_id",
                (pathway_id, version),
            ).fetchall()

        prerequisite_map: dict[str, list[str]] = {}
        for item in prerequisites:
            prerequisite_map.setdefault(item["unit_id"], []).append(item["prerequisite_unit_id"])
        capability_map: dict[str, dict[str, list[str]]] = {}
        for item in capabilities:
            capability_map.setdefault(item["unit_id"], {}).setdefault(item["relation_type"], []).append(item["capability_id"])
        evidence_map: dict[str, list[dict[str, str]]] = {}
        for item in evidence:
            evidence_map.setdefault(item["unit_id"], []).append(
                {"capability_id": item["capability_id"], "standard_id": item["standard_id"]}
            )

        return {
            **dict(path),
            "target_capability_ids": [item["capability_id"] for item in targets],
            "units": [
                {
                    **dict(item),
                    "source_module_ids": json.loads(item["source_module_ids_json"]),
                    "prerequisite_unit_ids": prerequisite_map.get(item["unit_id"], []),
                    "develops_capability_ids": capability_map.get(item["unit_id"], {}).get("develops", []),
                    "assesses_capability_ids": capability_map.get(item["unit_id"], {}).get("assesses", []),
                    "evidence_requirements": evidence_map.get(item["unit_id"], []),
                }
                for item in units
            ],
            "decisions": [dict(item) for item in decisions],
        }

    def active_path(self, pathway_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM learning_paths WHERE pathway_id = ? AND status = 'active'",
                (pathway_id,),
            ).fetchone()
        return self.get(pathway_id, row["version"]) if row else None
