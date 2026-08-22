"""Typed OpenAI learning-design worker for the reviewed Learning Graph.

The agent may compose a candidate sequence from active capability definitions and
existing delivery assets. The Learning Graph performs all authority, prerequisite,
evidence-standard, and activation checks after generation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.learning_graph import EvidenceRequirement, LearningPathDefinition, LearningUnit


class EvidenceRequirementOutput(BaseModel):
    capability_id: str
    standard_id: str


class LearningUnitOutput(BaseModel):
    unit_id: str
    kind: Literal["sprint", "lab", "mission"]
    title: str
    purpose: str
    develops_capability_ids: list[str] = Field(min_length=1, max_length=12)
    evidence_requirements: list[EvidenceRequirementOutput] = Field(default_factory=list, max_length=12)
    prerequisite_unit_ids: list[str] = Field(default_factory=list, max_length=12)
    source_module_ids: list[str] = Field(default_factory=list, max_length=12)


class LearningPathOutput(BaseModel):
    pathway_id: str
    version: str
    title: str
    target_capability_ids: list[str] = Field(min_length=1, max_length=30)
    units: list[LearningUnitOutput] = Field(min_length=1, max_length=40)
    design_notes: list[str] = Field(default_factory=list, max_length=10)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class LearningDesignContext:
    pathway_id: str
    version: str
    title: str
    active_capabilities: tuple[dict[str, Any], ...]
    existing_modules: tuple[dict[str, Any], ...] = ()

    def as_payload(self) -> dict[str, Any]:
        return {
            "pathway_id": self.pathway_id,
            "version": self.version,
            "title": self.title,
            "active_capabilities": list(self.active_capabilities),
            "existing_modules": list(self.existing_modules),
        }


def build_learning_design_agent(model: str | None = None) -> Any:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_LEARNING_MODEL", "gpt-5.6-sol")
    return Agent(
        name="Learning Graph Design Agent",
        model=model_name,
        instructions=(
            "Compose a compact learning path only from the active capabilities and evidence standards supplied in INPUT_JSON. "
            "Use existing modules as reusable delivery assets when they fit, but do not treat module titles as capability definitions. "
            "Use sprints for focused instruction, labs for bounded practice, and missions for work-like performance. "
            "Every target capability must be developed and must have at least one mission tied to one of that capability's supplied evidence standards. "
            "Do not invent capability IDs or evidence-standard IDs. Keep prerequisite edges acyclic. "
            "Do not issue credentials, employment claims, or curriculum approval. Return a candidate path only; deterministic validation and human activation happen elsewhere."
        ),
        output_type=LearningPathOutput,
    )


class OpenAILearningDesignProvider:
    def __init__(self, agent: Any | None = None, runner: RunnerLike | None = None, *, max_turns: int = 8) -> None:
        self.agent = agent or build_learning_design_agent()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    def propose(self, context: LearningDesignContext) -> LearningPathDefinition:
        result = self.runner.run_sync(
            self.agent,
            "Design the candidate Learning Graph from this reviewed capability context.\n\nINPUT_JSON\n"
            + json.dumps(context.as_payload(), ensure_ascii=False, sort_keys=True),
            max_turns=self.max_turns,
        )
        output = result.final_output
        if not isinstance(output, LearningPathOutput):
            raise TypeError("learning design agent returned untyped output")
        if output.pathway_id != context.pathway_id or output.version != context.version:
            raise ValueError("learning design agent changed the pathway identity or version")
        allowed = {item.get("capability_id") for item in context.active_capabilities}
        if set(output.target_capability_ids) - allowed:
            raise ValueError("learning design agent introduced an unknown target capability")

        units = tuple(
            LearningUnit(
                unit_id=item.unit_id,
                kind=item.kind,
                title=item.title,
                purpose=item.purpose,
                develops_capability_ids=tuple(item.develops_capability_ids),
                evidence_requirements=tuple(
                    EvidenceRequirement(requirement.capability_id, requirement.standard_id)
                    for requirement in item.evidence_requirements
                ),
                prerequisite_unit_ids=tuple(item.prerequisite_unit_ids),
                source_module_ids=tuple(item.source_module_ids),
            )
            for item in output.units
        )
        return LearningPathDefinition(
            pathway_id=output.pathway_id,
            version=output.version,
            title=output.title,
            target_capability_ids=tuple(output.target_capability_ids),
            units=units,
        )
