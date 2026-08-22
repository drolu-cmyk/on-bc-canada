"""Typed tool-free agents for aggregate programme Outcomes Intelligence."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class OutcomeFinding(BaseModel):
    theme: str
    signal_type: Literal["positive", "friction", "uncertain"]
    evidence_metrics: list[str] = Field(min_length=1, max_length=10)
    interpretation: str
    research_question: str = ""


class OutcomesAnalysisOutput(BaseModel):
    status: Literal["material_signal", "no_material_signal", "insufficient_evidence"]
    findings: list[OutcomeFinding] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    summary: str


class OutcomesChallengeOutput(BaseModel):
    status: Literal["supports", "narrows", "rejects", "insufficient"]
    cautions: list[str] = Field(default_factory=list, max_length=12)
    surviving_questions: list[str] = Field(default_factory=list, max_length=10)
    summary: str


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class OutcomesAgentSet:
    analysis_agent: Any
    challenge_agent: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return task + "\n\nINPUT_JSON\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_outcomes_agents(model: str | None = None) -> OutcomesAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_OUTCOMES_MODEL", "gpt-5.6-sol")
    boundary = (
        "Use only the supplied privacy-released aggregate programme metrics. Do not infer or reconstruct an individual learner, cohort identity, protected characteristic, disability, health status, immigration status, or employment outcome. "
        "Suppressed values are unavailable evidence, not zeros. Do not estimate them. Do not turn correlation into causation. "
        "You may interpret programme-level signals and formulate research questions only. You cannot change curriculum, learner records, credentials, or Work Intelligence. "
    )
    analysis = Agent(
        name="Outcomes Analysis Agent",
        model=model_name,
        instructions=boundary + (
            "Identify material programme-level signals only when the released metrics support them. Separate positive signals, friction, and uncertainty. "
            "Reference metrics descriptively in evidence_metrics. If a signal could justify investigation, phrase a narrow research question rather than a curriculum recommendation."
        ),
        output_type=OutcomesAnalysisOutput,
    )
    challenge = Agent(
        name="Outcomes Challenge Agent",
        model=model_name,
        instructions=boundary + (
            "Challenge the supplied outcomes interpretation. Look for denominator problems, suppression, survivorship or selection effects, path-version differences, incomplete observation windows, measurement mismatch, and alternative explanations. "
            "Reject a material-signal interpretation when the aggregate evidence cannot support it. Preserve only research questions that survive the challenge."
        ),
        output_type=OutcomesChallengeOutput,
    )
    return OutcomesAgentSet(analysis, challenge)


class OpenAIOutcomesIntelligenceProvider:
    def __init__(self, agents: OutcomesAgentSet | None = None, runner: RunnerLike | None = None, *, max_turns: int = 6) -> None:
        self.agents = agents or build_outcomes_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    def _run(self, agent: Any, task: str, payload: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, payload), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"outcomes agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def analyze_outcomes(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.analysis_agent,
            "Interpret the released programme outcomes without learner-level inference.",
            {"aggregate_outcomes": snapshot},
            OutcomesAnalysisOutput,
        )

    def challenge_outcomes(self, snapshot: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.challenge_agent,
            "Challenge the programme outcomes interpretation and preserve only defensible research questions.",
            {"aggregate_outcomes": snapshot, "analysis": analysis},
            OutcomesChallengeOutput,
        )
