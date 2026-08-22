"""RDS Data API implementation of the reviewed Capability Graph store contract."""
from __future__ import annotations

import json
from typing import Any

from runtime.capability_graph import (
    CapabilityDraft,
    CapabilityProvenance,
    CapabilityStatus,
    EvidenceStandard,
)
from runtime.rds_data_api import DomainDataApiConfig, RdsDataApi


class PostgresCapabilityGraphStore:
    STORE_VERSION = "0.2.0"

    def __init__(self, api: RdsDataApi | None = None) -> None:
        self.api = api or RdsDataApi(DomainDataApiConfig.from_environment(access_profile="learning"))

    def draft_from_work_intelligence(
        self,
        *,
        work_store: Any,
        pathway_id: str,
        pathway_name: str,
        capability_id: str,
        capability_name: str,
        description: str,
        target_level: str,
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
        with self.api.transaction() as tx:
            existing = self.api.query(
                "SELECT status FROM learning.capabilities WHERE capability_id=:capability_id",
                parameters={"capability_id": definition.capability_id},
                transaction_id=tx,
            )
            if existing and existing[0]["status"] in {"active", "retired"}:
                raise ValueError("active or retired capability definitions cannot be overwritten by an agent draft")
            for prerequisite_id in definition.prerequisite_ids:
                rows = self.api.query(
                    "SELECT capability_id FROM learning.capabilities WHERE capability_id=:capability_id",
                    parameters={"capability_id": prerequisite_id},
                    transaction_id=tx,
                )
                if not rows:
                    raise ValueError(f"unknown prerequisite capability: {prerequisite_id}")

            self.api.execute(
                """
                INSERT INTO learning.capabilities (
                    capability_id, pathway_id, name, description, target_level,
                    status, source_confidence, store_version
                ) VALUES (
                    :capability_id, :pathway_id, :name, :description, :target_level,
                    'draft', :source_confidence, :store_version
                )
                ON CONFLICT (capability_id) DO UPDATE SET
                    pathway_id=EXCLUDED.pathway_id,
                    name=EXCLUDED.name,
                    description=EXCLUDED.description,
                    target_level=EXCLUDED.target_level,
                    status='draft',
                    source_confidence=EXCLUDED.source_confidence,
                    store_version=EXCLUDED.store_version,
                    updated_at=now()
                """,
                parameters={
                    "capability_id": definition.capability_id,
                    "pathway_id": definition.pathway_id,
                    "name": definition.name,
                    "description": definition.description,
                    "target_level": definition.target_level,
                    "source_confidence": definition.source_confidence,
                    "store_version": self.STORE_VERSION,
                },
                transaction_id=tx,
            )
            for table in (
                "learning.capability_prerequisites",
                "learning.capability_evidence_standards",
                "learning.capability_provenance",
            ):
                self.api.execute(
                    f"DELETE FROM {table} WHERE capability_id=:capability_id",
                    parameters={"capability_id": definition.capability_id},
                    transaction_id=tx,
                )

            for prerequisite_id in definition.prerequisite_ids:
                self.api.execute(
                    """
                    INSERT INTO learning.capability_prerequisites (capability_id, prerequisite_id)
                    VALUES (:capability_id, :prerequisite_id)
                    """,
                    parameters={"capability_id": definition.capability_id, "prerequisite_id": prerequisite_id},
                    transaction_id=tx,
                )
            for standard in definition.evidence_standards:
                self.api.execute(
                    """
                    INSERT INTO learning.capability_evidence_standards (
                        capability_id, standard_id, description, artifact_types, minimum_level,
                        requires_defense, requires_revision, requires_changed_scenario
                    ) VALUES (
                        :capability_id, :standard_id, :description,
                        ARRAY(SELECT jsonb_array_elements_text(CAST(:artifact_types AS jsonb))),
                        :minimum_level, :requires_defense, :requires_revision, :requires_changed_scenario
                    )
                    """,
                    parameters={
                        "capability_id": definition.capability_id,
                        "standard_id": standard.standard_id,
                        "description": standard.description,
                        "artifact_types": list(standard.artifact_types),
                        "minimum_level": standard.minimum_level,
                        "requires_defense": standard.requires_defense,
                        "requires_revision": standard.requires_revision,
                        "requires_changed_scenario": standard.requires_changed_scenario,
                    },
                    transaction_id=tx,
                )
            for item in definition.provenance:
                self.api.execute(
                    """
                    INSERT INTO learning.capability_provenance (
                        capability_id, execution_id, relation_id, confidence
                    ) VALUES (:capability_id, :execution_id, :relation_id, :confidence)
                    """,
                    parameters={
                        "capability_id": definition.capability_id,
                        "execution_id": item.execution_id,
                        "relation_id": item.relation_id,
                        "confidence": item.confidence,
                    },
                    transaction_id=tx,
                )

    def activate(self, capability_id: str, *, approver_id: str, note: str = "") -> dict[str, Any]:
        if not approver_id.strip():
            raise ValueError("human approver ID is required")
        with self.api.transaction() as tx:
            rows = self.api.query(
                "SELECT status FROM learning.capabilities WHERE capability_id=:capability_id FOR UPDATE",
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            if not rows:
                raise KeyError(f"capability not found: {capability_id}")
            if rows[0]["status"] != "draft":
                raise ValueError("only draft capabilities can be activated")
            counts = self.api.query(
                """
                SELECT
                  (SELECT count(*) FROM learning.capability_evidence_standards WHERE capability_id=:capability_id) AS evidence_count,
                  (SELECT count(*) FROM learning.capability_provenance WHERE capability_id=:capability_id) AS provenance_count
                """,
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )[0]
            if int(counts["evidence_count"]) < 1:
                raise ValueError("capability has no evidence standard")
            if int(counts["provenance_count"]) < 1:
                raise ValueError("capability has no Work Intelligence provenance")
            prerequisites = self.api.query(
                """
                SELECT c.capability_id, c.status
                FROM learning.capability_prerequisites p
                JOIN learning.capabilities c ON c.capability_id=p.prerequisite_id
                WHERE p.capability_id=:capability_id
                """,
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            inactive = [item["capability_id"] for item in prerequisites if item["status"] != "active"]
            if inactive:
                raise ValueError(f"prerequisites must be active before activation: {sorted(inactive)}")
            self.api.execute(
                "UPDATE learning.capabilities SET status='active', updated_at=now() WHERE capability_id=:capability_id",
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            self.api.execute(
                """
                INSERT INTO learning.capability_decisions (capability_id, decision, approver_id, note)
                VALUES (:capability_id, 'activate', :approver_id, :note)
                """,
                parameters={"capability_id": capability_id, "approver_id": approver_id, "note": note},
                transaction_id=tx,
            )
        return self.get(capability_id)

    def retire(self, capability_id: str, *, approver_id: str, note: str) -> dict[str, Any]:
        if not approver_id.strip() or not note.strip():
            raise ValueError("retirement requires an accountable human and reason")
        with self.api.transaction() as tx:
            rows = self.api.query(
                "SELECT status FROM learning.capabilities WHERE capability_id=:capability_id FOR UPDATE",
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            if not rows:
                raise KeyError(f"capability not found: {capability_id}")
            if rows[0]["status"] != "active":
                raise ValueError("only active capabilities can be retired")
            dependents = self.api.query(
                """
                SELECT p.capability_id
                FROM learning.capability_prerequisites p
                JOIN learning.capabilities c ON c.capability_id=p.capability_id
                WHERE p.prerequisite_id=:capability_id AND c.status='active'
                """,
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            if dependents:
                raise ValueError("capability cannot be retired while active capabilities depend on it")
            self.api.execute(
                "UPDATE learning.capabilities SET status='retired', updated_at=now() WHERE capability_id=:capability_id",
                parameters={"capability_id": capability_id},
                transaction_id=tx,
            )
            self.api.execute(
                """
                INSERT INTO learning.capability_decisions (capability_id, decision, approver_id, note)
                VALUES (:capability_id, 'retire', :approver_id, :note)
                """,
                parameters={"capability_id": capability_id, "approver_id": approver_id, "note": note},
                transaction_id=tx,
            )
        return self.get(capability_id)

    def get(self, capability_id: str) -> dict[str, Any]:
        rows = self.api.query(
            """
            SELECT capability_id, pathway_id, name, description, target_level, status,
                   source_confidence, store_version, created_at::text AS created_at,
                   updated_at::text AS updated_at
            FROM learning.capabilities WHERE capability_id=:capability_id
            """,
            parameters={"capability_id": capability_id},
        )
        if not rows:
            raise KeyError(f"capability not found: {capability_id}")
        row = rows[0]
        prerequisites = self.api.query(
            """
            SELECT prerequisite_id FROM learning.capability_prerequisites
            WHERE capability_id=:capability_id ORDER BY prerequisite_id
            """,
            parameters={"capability_id": capability_id},
        )
        evidence = self.api.query(
            """
            SELECT capability_id, standard_id, description,
                   array_to_json(artifact_types)::text AS artifact_types_json,
                   minimum_level, requires_defense, requires_revision, requires_changed_scenario,
                   created_at::text AS created_at
            FROM learning.capability_evidence_standards
            WHERE capability_id=:capability_id ORDER BY standard_id
            """,
            parameters={"capability_id": capability_id},
        )
        provenance = self.api.query(
            """
            SELECT capability_id, execution_id, relation_id, confidence, created_at::text AS created_at
            FROM learning.capability_provenance
            WHERE capability_id=:capability_id ORDER BY execution_id, relation_id
            """,
            parameters={"capability_id": capability_id},
        )
        decisions = self.api.query(
            """
            SELECT decision, approver_id, note, decided_at::text AS decided_at
            FROM learning.capability_decisions
            WHERE capability_id=:capability_id ORDER BY decision_id
            """,
            parameters={"capability_id": capability_id},
        )
        return {
            **row,
            "source_confidence": float(row["source_confidence"]),
            "prerequisite_ids": [item["prerequisite_id"] for item in prerequisites],
            "evidence_standards": [
                {
                    **item,
                    "artifact_types": json.loads(item["artifact_types_json"]),
                    "requires_defense": bool(item["requires_defense"]),
                    "requires_revision": bool(item["requires_revision"]),
                    "requires_changed_scenario": bool(item["requires_changed_scenario"]),
                }
                for item in evidence
            ],
            "provenance": [{**item, "confidence": float(item["confidence"])} for item in provenance],
            "decisions": decisions,
        }

    def list_pathway(self, pathway_id: str, *, status: CapabilityStatus | None = None) -> list[dict[str, Any]]:
        sql = "SELECT capability_id FROM learning.capabilities WHERE pathway_id=:pathway_id"
        parameters: dict[str, Any] = {"pathway_id": pathway_id}
        if status is not None:
            sql += " AND status=:status"
            parameters["status"] = status
        sql += " ORDER BY capability_id"
        rows = self.api.query(sql, parameters=parameters)
        return [self.get(item["capability_id"]) for item in rows]
