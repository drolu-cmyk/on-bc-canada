"""Read-only career intelligence built from accepted capability evidence.

This module does not inspect raw learner submissions. It joins human-accepted
capability evidence to reviewed capability definitions and Work Intelligence role
relationships, producing a deidentified context for learner-facing career support.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.capability_graph import CapabilityGraphStore
from runtime.learner_progress_store import LearnerProgressStore
from runtime.work_intelligence import WorkIntelligenceStore


@dataclass(frozen=True)
class CareerCapabilityEvidence:
    capability_id: str
    capability_name: str
    target_level: str
    standard_id: str
    standard_description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "capability_name": self.capability_name,
            "target_level": self.target_level,
            "standard_id": self.standard_id,
            "standard_description": self.standard_description,
        }


@dataclass(frozen=True)
class RoleEvidenceAlignment:
    role_name: str
    required_capabilities: tuple[str, ...]
    signaled_capabilities: tuple[str, ...]
    matched_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    evidence_alignment: float
    relation_ids: tuple[str, ...]
    research_execution_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role_name": self.role_name,
            "required_capabilities": list(self.required_capabilities),
            "signaled_capabilities": list(self.signaled_capabilities),
            "matched_capabilities": list(self.matched_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "evidence_alignment": self.evidence_alignment,
            "relation_ids": list(self.relation_ids),
            "research_execution_ids": list(self.research_execution_ids),
        }


@dataclass(frozen=True)
class CareerModelContext:
    pathway_id: str
    learning_version: str
    accepted_capabilities: tuple[CareerCapabilityEvidence, ...]
    role_alignments: tuple[RoleEvidenceAlignment, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pathway_id": self.pathway_id,
            "learning_version": self.learning_version,
            "accepted_capabilities": [item.as_dict() for item in self.accepted_capabilities],
            "role_alignments": [item.as_dict() for item in self.role_alignments],
            "boundary": {
                "alignment_is_not_hiring_likelihood": True,
                "no_employer_decision": True,
                "no_external_application_or_contact": True,
                "no_immigration_or_licensing_conclusion": True,
            },
        }


class CareerIntelligenceBuilder:
    def __init__(
        self,
        *,
        learner_store: LearnerProgressStore,
        capability_store: CapabilityGraphStore,
        work_store: WorkIntelligenceStore,
    ) -> None:
        self.learner_store = learner_store
        self.capability_store = capability_store
        self.work_store = work_store

    def build(self, instance_id: str) -> CareerModelContext:
        instance = self.learner_store.get_instance(instance_id)
        accepted = self.learner_store.accepted_capability_evidence(instance_id)
        if not accepted:
            raise ValueError("career mobility requires at least one human-accepted capability evidence record")

        capability_evidence: list[CareerCapabilityEvidence] = []
        accepted_names: set[str] = set()
        candidate_role_ids: set[str] = set()

        for evidence in accepted:
            capability = self.capability_store.get(evidence["capability_id"])
            standard = next(
                (
                    item
                    for item in capability["evidence_standards"]
                    if item["standard_id"] == evidence["standard_id"]
                ),
                None,
            )
            if standard is None:
                raise ValueError(
                    f"accepted evidence no longer resolves to reviewed standard: {evidence['capability_id']}:{evidence['standard_id']}"
                )
            capability_evidence.append(
                CareerCapabilityEvidence(
                    capability_id=evidence["capability_id"],
                    capability_name=capability["name"],
                    target_level=capability["target_level"],
                    standard_id=evidence["standard_id"],
                    standard_description=standard["description"],
                )
            )
            accepted_names.add(capability["name"].casefold())

            work_capability = self.work_store.find_entity("capability", capability["name"])
            if work_capability is None:
                continue
            for relation in self.work_store.relations_for_entity(work_capability["entity_id"]):
                if (
                    relation["target_entity_id"] == work_capability["entity_id"]
                    and relation["relation_type"] in {"requires_capability", "signals_capability"}
                    and relation["status"] == "active"
                ):
                    candidate_role_ids.add(relation["source_entity_id"])

        alignments = [self._alignment_for_role(role_id, accepted_names) for role_id in candidate_role_ids]
        alignments.sort(key=lambda item: (-item.evidence_alignment, item.role_name.casefold()))

        return CareerModelContext(
            pathway_id=instance["pathway_id"],
            learning_version=instance["learning_version"],
            accepted_capabilities=tuple(
                sorted(
                    capability_evidence,
                    key=lambda item: (item.capability_name.casefold(), item.standard_id),
                )
            ),
            role_alignments=tuple(alignments),
        )

    def _alignment_for_role(self, role_entity_id: str, accepted_names: set[str]) -> RoleEvidenceAlignment:
        relations = self.work_store.relations_for_entity(role_entity_id)
        role_name: str | None = None
        required: set[str] = set()
        signaled: set[str] = set()
        relation_ids: set[str] = set()
        execution_ids: set[str] = set()

        for relation in relations:
            if relation["source_entity_id"] != role_entity_id or relation["status"] != "active":
                continue
            if relation["relation_type"] not in {"requires_capability", "signals_capability"}:
                continue
            role_name = relation["source_name"]
            capability_name = relation["target_name"]
            if relation["relation_type"] == "requires_capability":
                required.add(capability_name)
            else:
                signaled.add(capability_name)
            relation_ids.add(relation["relation_id"])
            execution_ids.add(relation["execution_id"])

        if not role_name:
            raise ValueError(f"role entity has no active capability relationships: {role_entity_id}")

        considered = required or signaled
        matched = {name for name in considered if name.casefold() in accepted_names}
        missing = considered - matched
        alignment = round(len(matched) / len(considered), 3) if considered else 0.0

        return RoleEvidenceAlignment(
            role_name=role_name,
            required_capabilities=tuple(sorted(required, key=str.casefold)),
            signaled_capabilities=tuple(sorted(signaled, key=str.casefold)),
            matched_capabilities=tuple(sorted(matched, key=str.casefold)),
            missing_capabilities=tuple(sorted(missing, key=str.casefold)),
            evidence_alignment=alignment,
            relation_ids=tuple(sorted(relation_ids)),
            research_execution_ids=tuple(sorted(execution_ids)),
        )
