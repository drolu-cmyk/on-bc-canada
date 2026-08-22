"""RDS Data API implementation of the Work Intelligence store contract."""
from __future__ import annotations

import json
from typing import Any

from runtime.graph_kernel import GraphExecution
from runtime.rds_data_api import DomainDataApiConfig, RdsDataApi
from runtime.work_intelligence import _entity_id, _relation_id


class PostgresWorkIntelligenceStore:
    STORE_VERSION = "0.2.0"

    def __init__(self, api: RdsDataApi | None = None) -> None:
        self.api = api or RdsDataApi(DomainDataApiConfig.from_environment(access_profile="intelligence"))

    @staticmethod
    def _metadata(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        raise RuntimeError("PostgreSQL metadata is not an object")

    def _upsert_entity(
        self,
        entity_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        *,
        transaction_id: str | None = None,
    ) -> str:
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValueError("entity name is required")
        entity_id = _entity_id(entity_type, clean_name)
        rows = self.api.query(
            "SELECT metadata::text AS metadata_json FROM intelligence.work_entities WHERE entity_id=:entity_id",
            parameters={"entity_id": entity_id},
            transaction_id=transaction_id,
        )
        merged = self._metadata(rows[0]["metadata_json"]) if rows else {}
        merged.update(metadata or {})
        self.api.execute(
            """
            INSERT INTO intelligence.work_entities (
                entity_id, entity_type, canonical_name, metadata
            ) VALUES (:entity_id, :entity_type, :canonical_name, CAST(:metadata AS jsonb))
            ON CONFLICT (entity_id) DO UPDATE SET
                canonical_name=EXCLUDED.canonical_name,
                metadata=EXCLUDED.metadata,
                updated_at=now()
            """,
            parameters={
                "entity_id": entity_id,
                "entity_type": entity_type,
                "canonical_name": clean_name,
                "metadata": merged,
            },
            transaction_id=transaction_id,
        )
        return entity_id

    def upsert_entity(self, entity_type: str, name: str, metadata: dict[str, Any] | None = None) -> str:
        return self._upsert_entity(entity_type, name, metadata)

    def ingest_research_execution(
        self,
        execution: GraphExecution,
        *,
        pathway_id: str,
        pathway_name: str,
    ) -> dict[str, Any]:
        self._assert_ingestable(execution)
        existing = self.api.query(
            "SELECT relation_count, confidence FROM intelligence.research_ingests WHERE execution_id=:execution_id",
            parameters={"execution_id": execution.execution_id},
        )
        if existing:
            return {
                "execution_id": execution.execution_id,
                "relation_count": int(existing[0]["relation_count"]),
                "confidence": float(existing[0]["confidence"]),
                "idempotent": True,
            }

        finding = execution.state["finding"]
        confidence = float(finding["confidence"])
        with self.api.transaction() as transaction_id:
            pathway_entity_id = self._upsert_entity(
                "pathway",
                pathway_name,
                {"pathway_id": pathway_id},
                transaction_id=transaction_id,
            )
            source_ids = self._store_sources(execution, transaction_id=transaction_id)
            relation_count = 0
            capability_ids: dict[str, str] = {}

            for capability in execution.state.get("capabilities", []):
                name = capability.get("capability")
                if not name:
                    continue
                capability_entity_id = self._upsert_entity(
                    "capability",
                    name,
                    {
                        "description": capability.get("description"),
                        "relevance": capability.get("relevance"),
                        "tool_neutral": capability.get("tool_neutral", True),
                    },
                    transaction_id=transaction_id,
                )
                capability_ids[name.casefold()] = capability_entity_id
                evidence_source_ids = capability.get("evidence_source_ids", [])
                relation_count += self._add_relation(
                    pathway_entity_id,
                    "develops_capability",
                    capability_entity_id,
                    confidence=confidence,
                    execution=execution,
                    source_ids=evidence_source_ids,
                    metadata={"pathway_id": pathway_id},
                    transaction_id=transaction_id,
                )
                for role_name in capability.get("relevant_roles", []):
                    role_id = self._upsert_entity("role", role_name, transaction_id=transaction_id)
                    relation_count += self._add_relation(
                        role_id,
                        "requires_capability",
                        capability_entity_id,
                        confidence=confidence,
                        execution=execution,
                        source_ids=evidence_source_ids,
                        transaction_id=transaction_id,
                    )

            for signal in execution.state.get("labour_market", {}).get("signals", []):
                role_name = signal.get("role")
                capability_hint = signal.get("capability_hint")
                if not role_name or not capability_hint:
                    continue
                role_id = self._upsert_entity(
                    "role",
                    role_name,
                    {"geography": signal.get("geography"), "signal": signal.get("signal")},
                    transaction_id=transaction_id,
                )
                capability_entity_id = capability_ids.get(capability_hint.casefold())
                if capability_entity_id is None:
                    capability_entity_id = self._upsert_entity(
                        "capability",
                        capability_hint,
                        {"source": "labour_market_signal"},
                        transaction_id=transaction_id,
                    )
                    capability_ids[capability_hint.casefold()] = capability_entity_id
                relation_count += self._add_relation(
                    role_id,
                    "signals_capability",
                    capability_entity_id,
                    confidence=confidence,
                    execution=execution,
                    source_ids=signal.get("source_ids", []),
                    metadata={
                        "signal": signal.get("signal"),
                        "geography": signal.get("geography"),
                        "note": signal.get("note"),
                    },
                    transaction_id=transaction_id,
                )

            for signal in execution.state.get("technology", {}).get("signals", []):
                technology_name = signal.get("technology")
                if not technology_name:
                    continue
                technology_id = self._upsert_entity(
                    "technology",
                    technology_name,
                    {
                        "maturity": signal.get("maturity"),
                        "relationship": signal.get("relationship"),
                    },
                    transaction_id=transaction_id,
                )
                relation_count += self._add_relation(
                    pathway_entity_id,
                    "has_technology_signal",
                    technology_id,
                    confidence=confidence,
                    execution=execution,
                    source_ids=signal.get("source_ids", []),
                    metadata={"maturity": signal.get("maturity"), "note": signal.get("note")},
                    transaction_id=transaction_id,
                )

            self.api.execute(
                """
                INSERT INTO intelligence.research_ingests (
                    execution_id, pathway_entity_id, confidence, relation_count, store_version
                ) VALUES (:execution_id, :pathway_entity_id, :confidence, :relation_count, :store_version)
                """,
                parameters={
                    "execution_id": execution.execution_id,
                    "pathway_entity_id": pathway_entity_id,
                    "confidence": confidence,
                    "relation_count": relation_count,
                    "store_version": self.STORE_VERSION,
                },
                transaction_id=transaction_id,
            )

        return {
            "execution_id": execution.execution_id,
            "pathway_entity_id": pathway_entity_id,
            "source_count": len(source_ids),
            "relation_count": relation_count,
            "confidence": confidence,
            "idempotent": False,
        }

    def _store_sources(self, execution: GraphExecution, *, transaction_id: str) -> set[str]:
        source_ids: set[str] = set()
        for source in execution.state.get("sources", []):
            source_id = source.get("source_id")
            if not source_id:
                continue
            source_ids.add(source_id)
            self.api.execute(
                """
                INSERT INTO intelligence.work_sources (
                    execution_id, source_id, publisher, title, url, metadata
                ) VALUES (
                    :execution_id, :source_id, :publisher, :title, :url, CAST(:metadata AS jsonb)
                )
                ON CONFLICT (execution_id, source_id) DO UPDATE SET
                    publisher=EXCLUDED.publisher,
                    title=EXCLUDED.title,
                    url=EXCLUDED.url,
                    metadata=EXCLUDED.metadata
                """,
                parameters={
                    "execution_id": execution.execution_id,
                    "source_id": source_id,
                    "publisher": source.get("publisher"),
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "metadata": source,
                },
                transaction_id=transaction_id,
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
        transaction_id: str,
    ) -> int:
        relation_id = _relation_id(source_entity_id, relation_type, target_entity_id, execution.execution_id)
        existing = self.api.query(
            "SELECT relation_id FROM intelligence.work_relations WHERE relation_id=:relation_id",
            parameters={"relation_id": relation_id},
            transaction_id=transaction_id,
        )
        if existing:
            return 0
        self.api.execute(
            """
            INSERT INTO intelligence.work_relations (
                relation_id, source_entity_id, relation_type, target_entity_id,
                confidence, execution_id, research_graph_version, metadata, status
            ) VALUES (
                :relation_id, :source_entity_id, :relation_type, :target_entity_id,
                :confidence, :execution_id, :research_graph_version, CAST(:metadata AS jsonb), 'active'
            )
            """,
            parameters={
                "relation_id": relation_id,
                "source_entity_id": source_entity_id,
                "relation_type": relation_type,
                "target_entity_id": target_entity_id,
                "confidence": confidence,
                "execution_id": execution.execution_id,
                "research_graph_version": execution.graph_version,
                "metadata": metadata or {},
            },
            transaction_id=transaction_id,
        )
        for source_id in sorted(set(source_ids)):
            self.api.execute(
                """
                INSERT INTO intelligence.relation_sources (relation_id, execution_id, source_id)
                SELECT :relation_id, :execution_id, :source_id
                WHERE EXISTS (
                    SELECT 1 FROM intelligence.work_sources
                    WHERE execution_id=:execution_id AND source_id=:source_id
                )
                ON CONFLICT DO NOTHING
                """,
                parameters={
                    "relation_id": relation_id,
                    "execution_id": execution.execution_id,
                    "source_id": source_id,
                },
                transaction_id=transaction_id,
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
        rows = self.api.query(
            """
            SELECT r.relation_id, r.source_entity_id, r.relation_type, r.target_entity_id,
                   r.confidence, r.execution_id, r.research_graph_version,
                   r.metadata::text AS metadata_json, r.status, r.created_at::text AS created_at,
                   s.canonical_name AS source_name, t.canonical_name AS target_name
            FROM intelligence.work_relations r
            JOIN intelligence.work_entities s ON s.entity_id=r.source_entity_id
            JOIN intelligence.work_entities t ON t.entity_id=r.target_entity_id
            WHERE r.source_entity_id=:entity_id OR r.target_entity_id=:entity_id
            ORDER BY r.relation_type, r.relation_id
            """,
            parameters={"entity_id": entity_id},
        )
        return [
            {
                **row,
                "confidence": float(row["confidence"]),
                "metadata": self._metadata(row.pop("metadata_json", "{}")),
            }
            for row in rows
        ]

    def find_entity(self, entity_type: str, name: str) -> dict[str, Any] | None:
        entity_id = _entity_id(entity_type, name)
        rows = self.api.query(
            """
            SELECT entity_id, entity_type, canonical_name, metadata::text AS metadata_json,
                   created_at::text AS created_at, updated_at::text AS updated_at
            FROM intelligence.work_entities
            WHERE entity_id=:entity_id
            """,
            parameters={"entity_id": entity_id},
        )
        if not rows:
            return None
        row = rows[0]
        metadata_json = row.pop("metadata_json", "{}")
        return {**row, "metadata": self._metadata(metadata_json), "metadata_json": metadata_json}
