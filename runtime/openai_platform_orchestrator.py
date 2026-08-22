"""Typed OpenAI manager that proposes a registered platform work type.

The manager only proposes a route from a metadata-only orchestration envelope.
PlatformGraphHarness remains the authority for whether that route, data boundary,
and requested effect are actually allowed.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.agent_identity_registry import ORCHESTRATOR_DATA, assert_agent_runtime_allowed
from runtime.model_runtime_telemetry import install_model_runtime_telemetry, model_runtime_context
from runtime.platform_graph_harness import DispatchMode


WorkType = Literal[
    "research_intelligence",
    "product_development",
    "business_operations",
    "learner_execution",
    "career_mobility",
    "employer_workforce",
    "outcomes_intelligence",
    "runtime_assurance",
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
    work_type: WorkType
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
            "Choose exactly one registered first-step work type for the supplied platform objective. "
            "The registered choices are research_intelligence, product_development, business_operations, learner_execution, career_mobility, employer_workforce, outcomes_intelligence, and runtime_assurance. "
            "Research_intelligence validates changing Canadian work, technology, and capability signals. Product_development coordinates product and platform design work. "
            "Business_operations covers growth, marketing, partnerships, operations, and finance analysis. Learner_execution handles deidentified coaching and evidence-readiness workflow. "
            "Career_mobility interprets already human-accepted capability evidence for learner guidance. Employer_workforce analyzes organization-level workflows and bounded AI adoption without employee decisions. "
            "Outcomes_intelligence interprets privacy-released aggregate programme outcomes and can formulate questions for independent Research Intelligence validation. "
            "Runtime_assurance interprets aggregate graph execution and control telemetry and can recommend human investigation or a Product Development remediation problem; it cannot change runtime policy. "
            "Choose the first necessary work type when an objective spans several stages; later handoffs are governed outside this model. "
            "Never invent a work type, side effect, authority level, data class, credential, hiring decision, financial action, production action, or external contact. "
            "Do not ask for raw learner submissions, direct learner identifiers, individual employee performance data, payment credentials, production secrets, raw prompts, or raw model outputs. "
            "Risk flags should identify boundary concerns visible from the envelope only. The deterministic platform graph harness makes the final routing decision."
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
        assert_agent_runtime_allowed(
            self.agent,
            requested_max_turns=self.max_turns,
            declared_model_data_classes=ORCHESTRATOR_DATA,
        )
        install_model_runtime_telemetry()
        prompt = (
            "Select the first registered platform work type for this metadata-only orchestration envelope.\n\n"
            "INPUT_JSON\n"
            + json.dumps(envelope.as_payload(), ensure_ascii=False, sort_keys=True)
        )
        with model_runtime_context(actor_id="platform-orchestrator-agent"):
            result = self.runner.run_sync(self.agent, prompt, max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, PlatformRouteOutput):
            raise TypeError("platform orchestrator returned untyped output")
        return output.model_dump()
