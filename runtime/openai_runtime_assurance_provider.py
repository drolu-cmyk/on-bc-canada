"""Typed tool-free agents for aggregate autonomous-platform Runtime Assurance."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ReliabilitySignal(BaseModel):
    graph_id: str
    severity: Literal["info", "watch", "high"]
    signal: str
    evidence: list[str] = Field(min_length=1, max_length=10)
    recommended_action: str


class RuntimeReliabilityOutput(BaseModel):
    status: Literal["healthy", "watch", "degraded", "insufficient_telemetry"]
    signals: list[ReliabilitySignal] = Field(default_factory=list, max_length=20)
    telemetry_gaps: list[str] = Field(default_factory=list, max_length=10)
    summary: str


class ControlSignal(BaseModel):
    control_area: Literal["identity", "authority", "tool_scope", "human_gate", "failure_handling", "telemetry", "budget", "configuration"]
    severity: Literal["info", "watch", "high"]
    signal: str
    evidence: list[str] = Field(min_length=1, max_length=10)
    recommended_action: str
    requires_human_change: bool = True


class RuntimeControlsOutput(BaseModel):
    status: Literal["pass", "watch", "intervention_recommended", "insufficient_telemetry"]
    signals: list[ControlSignal] = Field(default_factory=list, max_length=20)
    summary: str


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class RuntimeAssuranceAgentSet:
    reliability_agent: Any
    control_agent: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return task + "\n\nINPUT_JSON\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_runtime_assurance_agents(model: str | None = None) -> RuntimeAssuranceAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_RUNTIME_ASSURANCE_MODEL", "gpt-5.6-sol")
    boundary = (
        "Use only the supplied aggregate runtime telemetry and stated telemetry coverage. Do not infer prompt content, learner identity, hidden agent reasoning, credentials, or model cost when those fields are unavailable. "
        "Missing telemetry is a coverage gap, not evidence of health. You may recommend investigation or human runtime intervention only. "
        "You cannot disable an agent, change authority or tool scope, change runtime policy, mutate infrastructure, deploy code, or alter production. "
    )
    reliability = Agent(
        name="Runtime Reliability Agent",
        model=model_name,
        instructions=boundary + (
            "Assess execution completion, failure, approval-wait patterns, node progression, version spread, and telemetry gaps. Distinguish isolated failures from repeated graph-level degradation when the aggregate counts permit."
        ),
        output_type=RuntimeReliabilityOutput,
    )
    controls = Agent(
        name="Runtime Control Agent",
        model=model_name,
        instructions=boundary + (
            "Assess whether aggregate runtime evidence suggests identity, authority, tool-scope, human-gate, failure-handling, telemetry, budget, or configuration concerns. "
            "Do not claim a control failed merely because telemetry is missing. Recommend human review for any change to agent enablement, authority, tools, or runtime limits."
        ),
        output_type=RuntimeControlsOutput,
    )
    return RuntimeAssuranceAgentSet(reliability, controls)


class OpenAIRuntimeAssuranceProvider:
    def __init__(
        self,
        agents: RuntimeAssuranceAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 6,
    ) -> None:
        self.agents = agents or build_runtime_assurance_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    def _run(self, agent: Any, task: str, payload: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, payload), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"runtime assurance agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def analyze_reliability(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.reliability_agent,
            "Assess aggregate runtime reliability and telemetry completeness.",
            {"runtime_assurance": snapshot},
            RuntimeReliabilityOutput,
        )

    def analyze_controls(self, snapshot: dict[str, Any], reliability: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.control_agent,
            "Assess runtime control integrity from aggregate evidence without mutating controls.",
            {"runtime_assurance": snapshot, "reliability": reliability},
            RuntimeControlsOutput,
        )
