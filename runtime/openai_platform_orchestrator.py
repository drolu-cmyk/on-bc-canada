"""Typed OpenAI manager that proposes a registered platform workflow.

The manager only proposes a route from a metadata-only orchestration envelope.
PlatformHarness remains the authority for whether that route, data boundary, and
effect are actually allowed.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.platform_harness import DispatchMode


WorkflowKey = Literal[
    "research_evidence",
    "product_change",
    "business_operations",
    "learner_support",
    "career_mobility",
    "employer_workforce",
]


@dataclass(frozen=True)
class OrchestrationEnvelope:
    objective: str
    mode: DispatchMode
    requested_effect: str
    declared_data_classes: tuple[str, ...]

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


class PlatformRouteOutput(BaseModel):
    workflow_key: WorkflowKey
    reason: str
    required_inputs: list[str] = Field(default_factory=list, max_length=12)
    risk_flags: list[str] = Field(default_factory=list, max_length=12)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


def build_platform_orchestrator_agent(model: str | None = None) -> Any:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_ORCHESTRATOR_MODEL", "gpt-5.6-sol")
    return Agent(
        name="Platform Orchestrator Agent",
        model=model_name,
        instructions=(
            "Choose exactly one registered first-step workflow for the supplied platform objective. "
            "The registered choices are research_evidence, product_change, business_operations, learner_support, career_mobility, and employer_workforce. "
            "Research_evidence validates changing Canadian work, technology, and capability signals. Product_change coordinates product and platform design work. "
            "Business_operations covers growth, marketing, partnerships, operations, and finance analysis. Learner_support handles deidentified coaching and evidence-readiness workflow. "
            "Career_mobility interprets already human-accepted capability evidence for learner guidance. Employer_workforce analyzes organization-level workflows and AI adoption without employee decisions. "
            "Choose the first necessary workflow when an objective spans several stages; later handoffs are governed outside this model. "
            "Never invent a workflow, side effect, authority level, data class, credential, hiring decision, financial action, production action, or external contact. "
            "Do not ask for raw learner submissions, direct learner identifiers, individual employee performance data, payment credentials, or production secrets. "
            "Risk flags should identify boundary concerns visible from the envelope only. The deterministic platform harness makes the final routing decision."
        ),
        output_type=PlatformRouteOutput,
        tools=[],
    )


class OpenAIPlatformOrchestrator:
    def __init__(
        self,
        agent: Any | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 6,
    ) -> None:
        self.agent = agent or build_platform_orchestrator_agent()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    def propose(self, envelope: OrchestrationEnvelope) -> dict[str, Any]:
        if not envelope.objective.strip():
            raise ValueError("platform orchestration requires an objective")
        prompt = (
            "Select the first registered platform workflow for this metadata-only orchestration envelope.\n\n"
            "INPUT_JSON\n"
            + json.dumps(envelope.as_payload(), ensure_ascii=False, sort_keys=True)
        )
        result = self.runner.run_sync(self.agent, prompt, max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, PlatformRouteOutput):
            raise TypeError("platform orchestrator returned untyped output")
        return output.model_dump()
