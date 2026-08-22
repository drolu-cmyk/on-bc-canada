"""Reviewed capability graph for learner-facing capability definitions.

Work Intelligence establishes that a capability matters. This store defines what
the capability means, what must come before it, and what evidence can verify it.
Agents may create drafts from validated work evidence. Only an accountable human
can activate or retire a capability definition.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from runtime.work_intelligence import WorkIntelligenceStore


CapabilityLevel = Literal["explain", "apply", "analyze", "evaluate", "design", "defend"]
CapabilityStatus = Literal["draft", "active", "retired"]

_ALLOWED_LEVELS = {"explain", "apply", "analyze", "evaluate", "design", "defend"}
_ALLOWED_ARTIFACTS = {
    "brief",
    "diagram",
    "memo",
    "risk_register",
    "control_matrix",
    "lab_notebook",
    "evaluation_report",
    "presentation",
    "oral_defense",
    "portfolio",
}
_CAPABILITY_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,79}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class EvidenceStandard:
    standard_id: str
    description: str
    artifact_types: tuple[str, ...]
    minimum_level: CapabilityLevel
    requires_defense: bool = False
    requires_revision: bool = True
    requires_changed_scenario: bool = False

    def __post_init__(self) -> None:
        if not self.standard_id.strip():
            raise ValueError("evidence standard ID is required")
        if len(self.description.strip()) < 20:
            raise ValueError("evidence standard description must be specific")
        if not self.artifact_types:
            raise ValueError("at least one evidence artifact type is required")
        unknown = set(self.artifact_types) - _ALLOWED_ARTIFACTS
        if unknown:
            raise ValueError(f"unsupported evidence artifact types: {sorted(unknown)}")
        if self.minimum_level not in _ALLOWED_LEVELS:
            raise ValueError(f"unsupported capability level: {self.minimum_level}")


@dataclass(frozen=True)
class CapabilityProvenance:
    execution_id: str
    relation_id: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.relation_id.strip():
            raise ValueError("capability provenance requires an execution and relation")
        if not 0 <= self.confidence <= 1:
            raise ValueError("provenance confidence must be between 0 and 1")


@dataclass(frozen=True)
class CapabilityDraft:
    capability_id: str
    pathway_id: str
    name: str
    description: str
    target_level: CapabilityLevel
    evidence_standards: tuple[EvidenceStandard, ...]
    provenance: tuple[CapabilityProvenance, ...]
    prerequisite_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _CAPABILITY_ID.fullmatch(self.capability_id):
            raise ValueError("capability ID must be a stable lowercase dotted or hyphenated identifier")
        if not self.pathway_id.strip():
            raise ValueError("pathway ID is required")
        if len(self.name.strip()) < 3:
            raise ValueError("capability name is required")
        if len(self.description.strip()) < 20:
            raise ValueError("capability description must describe observable work")
        if self.target_level not in _ALLOWED_LEVELS:
            raise ValueError(f"unsupported target level: {self.target_level}")
        if not self.evidence_standards:
            raise ValueError("a capability requires at least one evidence standard")
        standard_ids = [item.standard_id for item in self.evidence_standards]
        if len(set(standard_ids)) != len(standard_ids):
            raise ValueError("duplicate evidence standard IDs are not allowed")
        if not self.provenance:
            raise ValueError("a capability draft requires Work Intelligence provenance")
        if self.capability_id in self.prerequisite_ids:
            raise ValueError("a capability cannot require itself")
        if len(set(self.prerequisite_ids)) != len(self.prerequisite_ids):
            raise ValueError("duplicate capability prerequisites are not allowed")

    @property
    def source_confidence(self) -> float:
        return max(item.confidence for item in self.provenance)


class CapabilityGraphStore:
    """Persist reviewed capability definitions and prerequisite edges."""

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
                CREATE TABLE IF NOT EXISTS capabilities (
                    capability_id TEXT PRIMARY KEY,
                    pathway_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_confidence REAL NOT NULL,
                    store_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS capability_prerequisites (
                    capability_id TEXT NOT NULL,
                    prerequisite_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(capability_id, prerequisite_id),
                    FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id),
                    FOREIGN KEY(prerequisite_id) REFERENCES capabilities(capability_id)
                );

                CREATE TABLE IF NOT EXISTS capability_evidence_standards (
                    capability_id TEXT NOT NULL,
                    standard_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    artifact_types_json TEXT NOT NULL,
                    minimum_level TEXT NOT NULL,
                    requires_defense INTEGER NOT NULL,
                    requires_revision INTEGER NOT NULL,
                    requires_changed_scenario INTEGER NOT NULL,
                    PRIMARY KEY(capability_id, standard_id),
                    FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id)
                );

                CREATE TABLE IF NOT EXISTS capability_provenance (
                    capability_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    relation_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    PRIMARY KEY(capability_id, execution_id, relation_id),
                    FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id)
                );

                CREATE TABLE IF NOT EXISTS capability_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    approver_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id)
                );
                """
            )

    def draft_from_work_intelligence(
        self,
        *,
        work_store: WorkIntelligenceStore,
        pathway_id: str,
        pathway_name: str,
        capability_id: str,
        capability_name: str,
        description: str,
        target_level: CapabilityLevel,
        evidence_standards: tuple[EvidenceStandard, ...],
        prerequisite_ids: tuple[str, ...] = (),
    ) -> CapabilityDraft:
        pathway = work_store.find_entity("pathway", pathway_name)
        capability = work_store.find_entity("capability", capability_name)
        if pathway is None or capability is None:
            raise ValueError("capability is not supported by the Work Intelligence Graph")
        stored_pathway_id = (pathway.get("metadata") or {}).get("pathway_id")
        if stored_pathway_id and stored_pathway_id != pathway_id:
            raise ValueError("pathway ID does not match the Work Intelligence pathway record")

        matching = [
            relation
            for relation in work_store.relations_for_entity(capability["entity_id"])
            if relation["source_entity_id"] == pathway["entity_id"]
            and relation["target_entity_id"] == capability["entity_id"]
            and relation["relation_type"] == "develops_capability"
            and relation["status"] == "active"
        ]
        if not matching:
            raise ValueError("capability has no active pathway evidence in Work Intelligence")

        provenance = tuple(
            CapabilityProvenance(
                execution_id=item["execution_id"],
                relation_id=item["relation_id"],
                confidence=float(item["confidence"]),
            )
            for item in sorted(matching, key=lambda value: (value["execution_id"], value["relation_id"]))
        )
        definition = CapabilityDraft(
            capability_id=capability_id,
            pathway_id=pathway_id,
            name=capability_name,
            description=description,
            target_level=target_level,
            evidence_standards=evidence_standards,
            prerequisite_ids=prerequisite_ids,
            provenance=provenance,
        )
        self.save_draft(definition)
        return definition

    def save_draft(self, definition: CapabilityDraft) -> None:
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT status FROM capabilities WHERE capability_id = ?",
                (definition.capability_id,),
            ).fetchone()
            if existing and existing["status"] in {"active", "retired"}:
                raise ValueError("active or retired capability definitions cannot be overwritten by an agent draft")

            for prerequisite_id in definition.prerequisite_ids:
                prerequisite = connection.execute(
                    "SELECT capability_id FROM capabilities WHERE capability_id = ?",
                    (prerequisite_id,),
                ).fetchone()
                if prerequisite is None:
                    raise ValueError(f"unknown prerequisite capability: {prerequisite_id}")

            connection.execute(
                """
                INSERT INTO capabilities (
                    capability_id, pathway_id, name, description, target_level,
                    status, source_confidence, store_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
                ON CONFLICT(capability_id) DO UPDATE SET
                    pathway_id=excluded.pathway_id,
                    name=excluded.name,
                    description=excluded.description,
                    target_level=excluded.target_level,
                    status='draft',
                    source_confidence=excluded.source_confidence,
                    store_version=excluded.store_version,
                    updated_at=excluded.updated_at
                """,
                (
                    definition.capability_id,
                    definition.pathway_id,
                    definition.name,
                    definition.description,
                    definition.target_level,
                    definition.source_confidence,
                    self.STORE_VERSION,
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM capability_prerequisites WHERE capability_id = ?", (definition.capability_id,))
            connection.execute("DELETE FROM capability_evidence_standards WHERE capability_id = ?", (definition.capability_id,))
            connection.execute("DELETE FROM capability_provenance WHERE capability_id = ?", (definition.capability_id,))

            for prerequisite_id in definition.prerequisite_ids:
                connection.execute(
                    "INSERT INTO capability_prerequisites (capability_id, prerequisite_id, created_at) VALUES (?, ?, ?)",
                    (definition.capability_id, prerequisite_id, now),
                )
            for standard in definition.evidence_standards:
                connection.execute(
                    """
                    INSERT INTO capability_evidence_standards (
                        capability_id, standard_id, description, artifact_types_json,
                        minimum_level, requires_defense, requires_revision,
                        requires_changed_scenario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.capability_id,
                        standard.standard_id,
                        standard.description,
                        _dumps(list(standard.artifact_types)),
                        standard.minimum_level,
                        int(standard.requires_defense),
                        int(standard.requires_revision),
                        int(standard.requires_changed_scenario),
                    ),
                )
            for item in definition.provenance:
                connection.execute(
                    """
                    INSERT INTO capability_provenance (
                        capability_id, execution_id, relation_id, confidence
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (definition.capability_id, item.execution_id, item.relation_id, item.confidence),
                )

    def activate(self, capability_id: str, *, approver_id: str, note: str = "") -> dict[str, Any]:
        if not approver_id.strip():
            raise ValueError("human approver ID is required")
        with self._connect() as connection:
            capability = connection.execute(
                "SELECT * FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if capability is None:
                raise KeyError(f"capability not found: {capability_id}")
            if capability["status"] != "draft":
                raise ValueError("only draft capabilities can be activated")

            evidence_count = connection.execute(
                "SELECT COUNT(*) AS count FROM capability_evidence_standards WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()["count"]
            provenance_count = connection.execute(
                "SELECT COUNT(*) AS count FROM capability_provenance WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()["count"]
            if evidence_count < 1:
                raise ValueError("capability has no evidence standard")
            if provenance_count < 1:
                raise ValueError("capability has no Work Intelligence provenance")

            prerequisites = connection.execute(
                """
                SELECT c.capability_id, c.status
                FROM capability_prerequisites p
                JOIN capabilities c ON c.capability_id = p.prerequisite_id
                WHERE p.capability_id = ?
                """,
                (capability_id,),
            ).fetchall()
            inactive = [item["capability_id"] for item in prerequisites if item["status"] != "active"]
            if inactive:
                raise ValueError(f"prerequisites must be active before activation: {sorted(inactive)}")

            now = _utc_now()
            connection.execute(
                "UPDATE capabilities SET status = 'active', updated_at = ? WHERE capability_id = ?",
                (now, capability_id),
            )
            connection.execute(
                """
                INSERT INTO capability_decisions (
                    capability_id, decision, approver_id, note, decided_at
                ) VALUES (?, 'activate', ?, ?, ?)
                """,
                (capability_id, approver_id, note, now),
            )
        return self.get(capability_id)

    def retire(self, capability_id: str, *, approver_id: str, note: str) -> dict[str, Any]:
        if not approver_id.strip() or not note.strip():
            raise ValueError("retirement requires an accountable human and reason")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"capability not found: {capability_id}")
            if row["status"] != "active":
                raise ValueError("only active capabilities can be retired")
            dependents = connection.execute(
                """
                SELECT p.capability_id
                FROM capability_prerequisites p
                JOIN capabilities c ON c.capability_id = p.capability_id
                WHERE p.prerequisite_id = ? AND c.status = 'active'
                """,
                (capability_id,),
            ).fetchall()
            if dependents:
                raise ValueError("capability cannot be retired while active capabilities depend on it")
            now = _utc_now()
            connection.execute(
                "UPDATE capabilities SET status = 'retired', updated_at = ? WHERE capability_id = ?",
                (now, capability_id),
            )
            connection.execute(
                """
                INSERT INTO capability_decisions (
                    capability_id, decision, approver_id, note, decided_at
                ) VALUES (?, 'retire', ?, ?, ?)
                """,
                (capability_id, approver_id, note, now),
            )
        return self.get(capability_id)

    def get(self, capability_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM capabilities WHERE capability_id = ?", (capability_id,)).fetchone()
            if row is None:
                raise KeyError(f"capability not found: {capability_id}")
            prerequisites = connection.execute(
                "SELECT prerequisite_id FROM capability_prerequisites WHERE capability_id = ? ORDER BY prerequisite_id",
                (capability_id,),
            ).fetchall()
            evidence = connection.execute(
                "SELECT * FROM capability_evidence_standards WHERE capability_id = ? ORDER BY standard_id",
                (capability_id,),
            ).fetchall()
            provenance = connection.execute(
                "SELECT * FROM capability_provenance WHERE capability_id = ? ORDER BY execution_id, relation_id",
                (capability_id,),
            ).fetchall()
            decisions = connection.execute(
                "SELECT decision, approver_id, note, decided_at FROM capability_decisions WHERE capability_id = ? ORDER BY decision_id",
                (capability_id,),
            ).fetchall()
        return {
            **dict(row),
            "prerequisite_ids": [item["prerequisite_id"] for item in prerequisites],
            "evidence_standards": [
                {
                    **dict(item),
                    "artifact_types": json.loads(item["artifact_types_json"]),
                    "requires_defense": bool(item["requires_defense"]),
                    "requires_revision": bool(item["requires_revision"]),
                    "requires_changed_scenario": bool(item["requires_changed_scenario"]),
                }
                for item in evidence
            ],
            "provenance": [dict(item) for item in provenance],
            "decisions": [dict(item) for item in decisions],
        }

    def list_pathway(self, pathway_id: str, *, status: CapabilityStatus | None = None) -> list[dict[str, Any]]:
        query = "SELECT capability_id FROM capabilities WHERE pathway_id = ?"
        params: list[Any] = [pathway_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY capability_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self.get(item["capability_id"]) for item in rows]
