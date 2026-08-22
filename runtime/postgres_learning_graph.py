"""RDS Data API implementation of the reviewed Learning Graph store contract."""
from __future__ import annotations

import json
from typing import Any

from runtime.learning_graph import LearningPathDefinition
from runtime.rds_data_api import DomainDataApiConfig, RdsDataApi


class PostgresLearningGraphStore:
    STORE_VERSION = "0.2.0"

    def __init__(self, api: RdsDataApi | None = None) -> None:
        self.api = api or RdsDataApi(DomainDataApiConfig.from_environment(access_profile="learning"))

    def save_candidate(self, definition: LearningPathDefinition, *, capabilities: Any) -> dict[str, Any]:
        capability_records = self._validate_against_capabilities(definition, capabilities)
        with self.api.transaction() as tx:
            existing = self.api.query(
                """
                SELECT status FROM learning.learning_paths
                WHERE pathway_id=:pathway_id AND version=:version
                FOR UPDATE
                """,
                parameters={"pathway_id": definition.pathway_id, "version": definition.version},
                transaction_id=tx,
            )
            if existing and existing[0]["status"] in {"active", "retired"}:
                raise ValueError("an active or retired learning path version cannot be replaced by an agent candidate")

            self.api.execute(
                """
                INSERT INTO learning.learning_paths (
                    pathway_id, version, title, status, store_version
                ) VALUES (:pathway_id, :version, :title, 'candidate', :store_version)
                ON CONFLICT (pathway_id, version) DO UPDATE SET
                    title=EXCLUDED.title,
                    status='candidate',
                    store_version=EXCLUDED.store_version,
                    updated_at=now()
                """,
                parameters={
                    "pathway_id": definition.pathway_id,
                    "version": definition.version,
                    "title": definition.title,
                    "store_version": self.STORE_VERSION,
                },
                transaction_id=tx,
            )

            for table in (
                "learning.learning_path_targets",
                "learning.learning_unit_evidence",
                "learning.learning_unit_prerequisites",
                "learning.learning_unit_capabilities",
                "learning.learning_units",
            ):
                self.api.execute(
                    f"DELETE FROM {table} WHERE pathway_id=:pathway_id AND version=:version",
                    parameters={"pathway_id": definition.pathway_id, "version": definition.version},
                    transaction_id=tx,
                )

            for capability_id in definition.target_capability_ids:
                self.api.execute(
                    """
                    INSERT INTO learning.learning_path_targets (pathway_id, version, capability_id)
                    VALUES (:pathway_id, :version, :capability_id)
                    """,
                    parameters={
                        "pathway_id": definition.pathway_id,
                        "version": definition.version,
                        "capability_id": capability_id,
                    },
                    transaction_id=tx,
                )

            # Persist all units before any unit-to-unit prerequisite edge.
            for unit in definition.units:
                self.api.execute(
                    """
                    INSERT INTO learning.learning_units (
                        pathway_id, version, unit_id, kind, title, purpose, source_module_ids
                    ) VALUES (
                        :pathway_id, :version, :unit_id, :kind, :title, :purpose,
                        ARRAY(SELECT jsonb_array_elements_text(CAST(:source_module_ids AS jsonb)))
                    )
                    """,
                    parameters={
                        "pathway_id": definition.pathway_id,
                        "version": definition.version,
                        "unit_id": unit.unit_id,
                        "kind": unit.kind,
                        "title": unit.title,
                        "purpose": unit.purpose,
                        "source_module_ids": list(unit.source_module_ids),
                    },
                    transaction_id=tx,
                )

            for unit in definition.units:
                for capability_id in unit.develops_capability_ids:
                    self.api.execute(
                        """
                        INSERT INTO learning.learning_unit_capabilities (
                            pathway_id, version, unit_id, capability_id, relation_type
                        ) VALUES (:pathway_id, :version, :unit_id, :capability_id, 'develops')
                        """,
                        parameters={
                            "pathway_id": definition.pathway_id,
                            "version": definition.version,
                            "unit_id": unit.unit_id,
                            "capability_id": capability_id,
                        },
                        transaction_id=tx,
                    )
                for prerequisite_id in unit.prerequisite_unit_ids:
                    self.api.execute(
                        """
                        INSERT INTO learning.learning_unit_prerequisites (
                            pathway_id, version, unit_id, prerequisite_unit_id
                        ) VALUES (:pathway_id, :version, :unit_id, :prerequisite_unit_id)
                        """,
                        parameters={
                            "pathway_id": definition.pathway_id,
                            "version": definition.version,
                            "unit_id": unit.unit_id,
                            "prerequisite_unit_id": prerequisite_id,
                        },
                        transaction_id=tx,
                    )
                for requirement in unit.evidence_requirements:
                    self.api.execute(
                        """
                        INSERT INTO learning.learning_unit_evidence (
                            pathway_id, version, unit_id, capability_id, standard_id
                        ) VALUES (:pathway_id, :version, :unit_id, :capability_id, :standard_id)
                        """,
                        parameters={
                            "pathway_id": definition.pathway_id,
                            "version": definition.version,
                            "unit_id": unit.unit_id,
                            "capability_id": requirement.capability_id,
                            "standard_id": requirement.standard_id,
                        },
                        transaction_id=tx,
                    )
                    self.api.execute(
                        """
                        INSERT INTO learning.learning_unit_capabilities (
                            pathway_id, version, unit_id, capability_id, relation_type
                        ) VALUES (:pathway_id, :version, :unit_id, :capability_id, 'assesses')
                        """,
                        parameters={
                            "pathway_id": definition.pathway_id,
                            "version": definition.version,
                            "unit_id": unit.unit_id,
                            "capability_id": requirement.capability_id,
                        },
                        transaction_id=tx,
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
        capabilities: Any,
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
        mission_coverage: dict[str, set[str]] = {
            capability_id: set() for capability_id in definition.target_capability_ids
        }
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
        with self.api.transaction() as tx:
            rows = self.api.query(
                """
                SELECT status FROM learning.learning_paths
                WHERE pathway_id=:pathway_id AND version=:version
                FOR UPDATE
                """,
                parameters={"pathway_id": pathway_id, "version": version},
                transaction_id=tx,
            )
            if not rows:
                raise KeyError(f"learning path not found: {pathway_id}@{version}")
            if rows[0]["status"] != "candidate":
                raise ValueError("only a candidate learning path can be activated")
            other_active = self.api.query(
                """
                SELECT version FROM learning.learning_paths
                WHERE pathway_id=:pathway_id AND status='active' AND version<>:version
                FOR UPDATE
                """,
                parameters={"pathway_id": pathway_id, "version": version},
                transaction_id=tx,
            )
            if other_active:
                raise ValueError(f"retire active learning path version before activation: {other_active[0]['version']}")
            self.api.execute(
                """
                UPDATE learning.learning_paths SET status='active', updated_at=now()
                WHERE pathway_id=:pathway_id AND version=:version
                """,
                parameters={"pathway_id": pathway_id, "version": version},
                transaction_id=tx,
            )
            self.api.execute(
                """
                INSERT INTO learning.learning_path_decisions (
                    pathway_id, version, decision, approver_id, note
                ) VALUES (:pathway_id, :version, 'activate', :approver_id, :note)
                """,
                parameters={
                    "pathway_id": pathway_id,
                    "version": version,
                    "approver_id": approver_id,
                    "note": note,
                },
                transaction_id=tx,
            )
        return self.get(pathway_id, version)

    def retire(self, pathway_id: str, version: str, *, approver_id: str, note: str) -> dict[str, Any]:
        if not approver_id.strip() or not note.strip():
            raise ValueError("learning path retirement requires an accountable human and reason")
        with self.api.transaction() as tx:
            rows = self.api.query(
                """
                SELECT status FROM learning.learning_paths
                WHERE pathway_id=:pathway_id AND version=:version
                FOR UPDATE
                """,
                parameters={"pathway_id": pathway_id, "version": version},
                transaction_id=tx,
            )
            if not rows:
                raise KeyError(f"learning path not found: {pathway_id}@{version}")
            if rows[0]["status"] != "active":
                raise ValueError("only an active learning path can be retired")
            self.api.execute(
                """
                UPDATE learning.learning_paths SET status='retired', updated_at=now()
                WHERE pathway_id=:pathway_id AND version=:version
                """,
                parameters={"pathway_id": pathway_id, "version": version},
                transaction_id=tx,
            )
            self.api.execute(
                """
                INSERT INTO learning.learning_path_decisions (
                    pathway_id, version, decision, approver_id, note
                ) VALUES (:pathway_id, :version, 'retire', :approver_id, :note)
                """,
                parameters={
                    "pathway_id": pathway_id,
                    "version": version,
                    "approver_id": approver_id,
                    "note": note,
                },
                transaction_id=tx,
            )
        return self.get(pathway_id, version)

    def get(self, pathway_id: str, version: str) -> dict[str, Any]:
        rows = self.api.query(
            """
            SELECT pathway_id, version, title, status, store_version,
                   created_at::text AS created_at, updated_at::text AS updated_at
            FROM learning.learning_paths
            WHERE pathway_id=:pathway_id AND version=:version
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        if not rows:
            raise KeyError(f"learning path not found: {pathway_id}@{version}")
        path = rows[0]
        targets = self.api.query(
            """
            SELECT capability_id FROM learning.learning_path_targets
            WHERE pathway_id=:pathway_id AND version=:version ORDER BY capability_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        units = self.api.query(
            """
            SELECT pathway_id, version, unit_id, kind, title, purpose,
                   array_to_json(source_module_ids)::text AS source_module_ids_json
            FROM learning.learning_units
            WHERE pathway_id=:pathway_id AND version=:version ORDER BY unit_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        prerequisites = self.api.query(
            """
            SELECT unit_id, prerequisite_unit_id FROM learning.learning_unit_prerequisites
            WHERE pathway_id=:pathway_id AND version=:version
            ORDER BY unit_id, prerequisite_unit_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        capabilities = self.api.query(
            """
            SELECT unit_id, capability_id, relation_type FROM learning.learning_unit_capabilities
            WHERE pathway_id=:pathway_id AND version=:version
            ORDER BY unit_id, relation_type, capability_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        evidence = self.api.query(
            """
            SELECT unit_id, capability_id, standard_id FROM learning.learning_unit_evidence
            WHERE pathway_id=:pathway_id AND version=:version
            ORDER BY unit_id, capability_id, standard_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )
        decisions = self.api.query(
            """
            SELECT decision, approver_id, note, decided_at::text AS decided_at
            FROM learning.learning_path_decisions
            WHERE pathway_id=:pathway_id AND version=:version ORDER BY decision_id
            """,
            parameters={"pathway_id": pathway_id, "version": version},
        )

        prerequisite_map: dict[str, list[str]] = {}
        for item in prerequisites:
            prerequisite_map.setdefault(item["unit_id"], []).append(item["prerequisite_unit_id"])
        capability_map: dict[str, dict[str, list[str]]] = {}
        for item in capabilities:
            capability_map.setdefault(item["unit_id"], {}).setdefault(item["relation_type"], []).append(
                item["capability_id"]
            )
        evidence_map: dict[str, list[dict[str, str]]] = {}
        for item in evidence:
            evidence_map.setdefault(item["unit_id"], []).append(
                {"capability_id": item["capability_id"], "standard_id": item["standard_id"]}
            )

        return {
            **path,
            "target_capability_ids": [item["capability_id"] for item in targets],
            "units": [
                {
                    **item,
                    "source_module_ids": json.loads(item["source_module_ids_json"]),
                    "prerequisite_unit_ids": prerequisite_map.get(item["unit_id"], []),
                    "develops_capability_ids": capability_map.get(item["unit_id"], {}).get("develops", []),
                    "assesses_capability_ids": capability_map.get(item["unit_id"], {}).get("assesses", []),
                    "evidence_requirements": evidence_map.get(item["unit_id"], []),
                }
                for item in units
            ],
            "decisions": decisions,
        }

    def active_path(self, pathway_id: str) -> dict[str, Any] | None:
        rows = self.api.query(
            """
            SELECT version FROM learning.learning_paths
            WHERE pathway_id=:pathway_id AND status='active'
            """,
            parameters={"pathway_id": pathway_id},
        )
        return self.get(pathway_id, rows[0]["version"]) if rows else None
