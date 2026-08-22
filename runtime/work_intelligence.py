"""Evidence-backed Work Intelligence Graph reference store.

Validated research becomes reusable role, capability, pathway, technology, and
source relationships. The first implementation uses SQLite so the domain model
can mature before a dedicated graph database is justified.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.graph_kernel import GraphExecution


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entity_id(entity_type: str, name: str) -> str:
    normalized = " ".join(name.casefold().split())
    digest = hashlib.sha256(f"{entity_type}:{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"{entity_type}:{digest}"


def _relation_id(source_id: str, relation_type: str, target_id: str, execution_id: str) -> str:
    value = f"{source_id}|{relation_type}|{target_id}|{execution_id}"
    return f"rel:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


class WorkIntelligenceStore:
    """Store versioned work relationships with research provenance."""

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
                CREATE TABLE IF NOT EXISTS work_entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(entity_type, canonical_name)
                );

                CREATE TABLE IF NOT EXISTS work_sources (
                    execution_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    publisher TEXT,
                    title TEXT,
                    url TEXT,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(execution_id, source_id)
                );

                CREATE TABLE IF NOT EXISTS work_relations (
                    relation_id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    execution_id TEXT NOT NULL,
                    research_graph_version TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_entity_id) REFERENCES work_entities(entity_id),
                    FOREIGN KEY(target_entity_id) REFERENCES work_entities(entity_id)
                );

                CREATE TABLE IF NOT EXISTS relation_sources (
                    relation_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    PRIMARY KEY(relation_id, execution_id, source_id),
                    FOREIGN KEY(relation_id) REFERENCES work_relations(relation_id),
                    FOREIGN KEY(execution_id, source_id) REFERENCES work_sources(execution_id, source_id)
                );

                CREATE TABLE IF NOT EXISTS research_ingests (
                    execution_id TEXT PRIMARY KEY,
                    pathway_entity_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    relation_count INTEGER NOT NULL,
                    store_version TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    FOREIGN KEY(pathway_entity_id) REFERENCES work_entities(entity_id)
                );
                """
            )

    def upsert_entity(self, entity_type: str, name: str, metadata: dict[str, Any] | None = None) -> str:
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValueError("entity name is required")
        entity_id = _entity_id(entity_type, clean_name)
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT metadata_json FROM work_entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            merged = json.loads(existing["metadata_json"]) if existing else {}
            merged.update(metadata or {})
            connection.execute(
                """
                INSERT INTO work_entities (
                    entity_id, entity_type, canonical_name, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    canonical_name=excluded.canonical_name,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (entity_id, entity_type, clean_name, _dumps(merged), now, now),
            )
        return entity_id

    def ingest_research_execution(
        self,
        execution: GraphExecution,
        *,
        pathway_id: str,
        pathway_name: str,
    ) -> dict[str, Any]:
        self._assert_ingestable(execution)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT relation_count, confidence FROM research_ingests WHERE execution_id = ?",
                (execution.execution_id,),
            ).fetchone()
        if existing:
            return {
                "execution_id": execution.execution_id,
                "relation_count": existing["relation_count"],
                "confidence": existing["confidence"],
                "idempotent": True,
            }

        finding = execution.state["finding"]
        confidence = float(finding["confidence"])
        pathway_entity_id = self.upsert_entity(
            "pathway",
            pathway_name,
            {"pathway_id": pathway_id},
        )
        source_ids = self._store_sources(execution)
        relation_count = 0

        capability_ids: dict[str, str] = {}
        for capability in execution.state.get("capabilities", []):
            name = capability.get("capability")
            if not name:
                continue
            capability_id = self.upsert_entity(
                "capability",
                name,
                {
                    "description": capability.get("description"),
                    "relevance": capability.get("relevance"),
                    "tool_neutral": capability.get("tool_neutral", True),
                },
            )
            capability_ids[name.casefold()] = capability_id
            evidence_source_ids = capability.get("evidence_source_ids", [])
            relation_count += self._add_relation(
                pathway_entity_id,
                "develops_capability",
                capability_id,
                confidence=confidence,
                execution=execution,
                source_ids=evidence_source_ids,
                metadata={"pathway_id": pathway_id},
            )
            for role_name in capability.get("relevant_roles", []):
                role_id = self.upsert_entity("role", role_name)
                relation_count += self._add_relation(
                    role_id,
                    "requires_capability",
                    capability_id,
                    confidence=confidence,
                    execution=execution,
                    source_ids=evidence_source_ids,
                )

        for signal in execution.state.get("labour_market", {}).get("signals", []):
            role_name = signal.get("role")
            capability_hint = signal.get("capability_hint")
            if not role_name or not capability_hint:
                continue
            role_id = self.upsert_entity(
                "role",
                role_name,
                {"geography": signal.get("geography"), "signal": signal.get("signal")},
            )
            capability_id = capability_ids.get(capability_hint.casefold())
            if capability_id is None:
                capability_id = self.upsert_entity(
                    "capability",
                    capability_hint,
                    {"source": "labour_market_signal"},
                )
                capability_ids[capability_hint.casefold()] = capability_id
            relation_count += self._add_relation(
                role_id,
                "signals_capability",
                capability_id,
                confidence=confidence,
                execution=execution,
                source_ids=signal.get("source_ids", []),
                metadata={
                    "signal": signal.get("signal"),
                    "geography": signal.get("geography"),
                    "note": signal.get("note"),
                },
            )

        for signal in execution.state.get("technology", {}).get("signals", []):
            technology_name = signal.get("technology")
            if not technology_name:
                continue
            technology_id = self.upsert_entity(
                "technology",
                technology_name,
                {
                    "maturity": signal.get("maturity"),
                    "relationship": signal.get("relationship"),
                },
            )
            relation_count += self._add_relation(
                pathway_entity_id,
                "has_technology_signal",
                technology_id,
                confidence=confidence,
                execution=execution,
                source_ids=signal.get("source_ids", []),
                metadata={
                    "maturity": signal.get("maturity"),
                    "note": signal.get("note"),
                },
            )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_ingests (
                    execution_id, pathway_entity_id, confidence, relation_count, store_version, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    pathway_entity_id,
                    confidence,
                    relation_count,
                    self.STORE_VERSION,
                    _utc_now(),
                ),
            )
        return {
            "execution_id": execution.execution_id,
            "pathway_entity_id": pathway_entity_id,
            "source_count": len(source_ids),
            "relation_count": relation_count,
            "confidence": confidence,
            "idempotent": False,
        }

    def _store_sources(self, execution: GraphExecution) -> set[str]:
        source_ids: set[str] = set()
        with self._connect() as connection:
            for source in execution.state.get("sources", []):
                source_id = source.get("source_id")
                if not source_id:
                    continue
                source_ids.add(source_id)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO work_sources (
                        execution_id, source_id, publisher, title, url, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution.execution_id,
                        source_id,
                        source.get("publisher"),
                        source.get("title"),
                        source.get("url"),
                        _dumps(source),
                    ),
                )
        return source_ids

    def _add_relation(
        self,
        source_entity_id: str,
        relation_type: str,
        target_entity_id: str,
        *,
        confidence: float,
        execution: GraphExecution,
        source_ids: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        relation_id = _relation_id(
            source_entity_id,
            relation_type,
            target_entity_id,
            execution.execution_id,
        )
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM work_relations WHERE relation_id = ?",
                (relation_id,),
            ).fetchone()
            if existing:
                return 0
            connection.execute(
                """
                INSERT INTO work_relations (
                    relation_id, source_entity_id, relation_type, target_entity_id,
                    confidence, execution_id, research_graph_version, metadata_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relation_id,
                    source_entity_id,
                    relation_type,
                    target_entity_id,
                    confidence,
                    execution.execution_id,
                    execution.graph_version,
                    _dumps(metadata or {}),
                    "active",
                    now,
                ),
            )
            for research_source_id in sorted(set(source_ids)):
                exists = connection.execute(
                    "SELECT 1 FROM work_sources WHERE execution_id = ? AND source_id = ?",
                    (execution.execution_id, research_source_id),
                ).fetchone()
                if exists:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO relation_sources (
                            relation_id, execution_id, source_id
                        ) VALUES (?, ?, ?)
                        """,
                        (relation_id, execution.execution_id, research_source_id),
                    )
        return 1

    @staticmethod
    def _assert_ingestable(execution: GraphExecution) -> None:
        if execution.status != "completed":
            raise ValueError("only completed research executions can enter work intelligence")
        if execution.state.get("research_status") != "complete" or "finding" not in execution.state:
            raise ValueError("research execution has no validated finding")
        impact = execution.state["finding"].get("curriculum_impact", {})
        recommendation = impact.get("recommendation", "no_change")
        if recommendation != "no_change":
            authorized = any(
                item.get("node_id") == "curriculum_review" and item.get("approved") is True
                for item in execution.history
            )
            if not authorized:
                raise ValueError("research change recommendation lacks human authorization")

    def relations_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, s.canonical_name AS source_name, t.canonical_name AS target_name
                FROM work_relations r
                JOIN work_entities s ON s.entity_id = r.source_entity_id
                JOIN work_entities t ON t.entity_id = r.target_entity_id
                WHERE r.source_entity_id = ? OR r.target_entity_id = ?
                ORDER BY r.relation_type, r.relation_id
                """,
                (entity_id, entity_id),
            ).fetchall()
        return [
            {
                **dict(row),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def find_entity(self, entity_type: str, name: str) -> dict[str, Any] | None:
        entity_id = _entity_id(entity_type, name)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM work_entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "metadata": json.loads(row["metadata_json"])}
