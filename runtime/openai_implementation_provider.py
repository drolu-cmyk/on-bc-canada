"""Typed OpenAI workers for the Implementation and Delivery Graph."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator


class ImplementationPlanOutput(BaseModel):
    objective: str
    change_slices: list[str] = Field(min_length=1, max_length=20)
    files_to_change: list[str] = Field(min_length=1, max_length=30)
    verification_ids: list[str] = Field(min_length=1, max_length=15)
    risks: list[str] = Field(default_factory=list, max_length=15)
    rollback_note: str


class FileChangeOutput(BaseModel):
    operation: Literal["create", "update", "delete"]
    path: str
    reason: str
    content: str | None = None
    expected_sha256: str | None = None

    @model_validator(mode="after")
    def validate_operation_shape(self):
        if self.operation in {"create", "update"} and self.content is None:
            raise ValueError("create and update changes require complete file content")
        if self.operation == "delete" and self.content is not None:
            raise ValueError("delete changes cannot include file content")
        if self.operation in {"update", "delete"} and not self.expected_sha256:
            raise ValueError("update and delete changes require an expected file hash")
        if self.operation == "create" and self.expected_sha256 is not None:
            raise ValueError("create changes cannot include an expected file hash")
        return self


class ChangeSetOutput(BaseModel):
    changes: list[FileChangeOutput] = Field(min_length=1, max_length=30)
    implementation_note: str


class ImplementationReviewOutput(BaseModel):
    status: Literal["pass", "warn", "block"]
    summary: str
    blockers: list[str] = Field(default_factory=list, max_length=15)
    warnings: list[str] = Field(default_factory=list, max_length=15)
    findings: list[str] = Field(default_factory=list, max_length=20)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ImplementationAgentSet:
    planner: Any
    generator: Any
    code_review: Any
    security_review: Any
    quality_review: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return f"{task}\n\nINPUT_JSON\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def build_implementation_agents(model: str | None = None) -> ImplementationAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_IMPLEMENTATION_MODEL", "gpt-5.6-sol")
    shared = (
        "Work only from the authorized release packet, supplied repository file snapshots, and registered verification identifiers. "
        "Do not assume access to files, services, secrets, GitHub, AWS, or a shell beyond the supplied context. "
        "Do not generate credentials or secret values. Preserve existing architecture unless the authorized release packet requires a change. "
        "Use provider-neutral, testable implementation patterns. Merge and production deployment remain human-authorized actions outside your authority. "
    )
    planner = Agent(
        name="Implementation Design Agent",
        model=model_name,
        instructions=shared + (
            "Turn the authorized release packet into small reversible implementation slices. Name only repository paths present in the supplied context or explicitly named as intended new files. "
            "Select verification identifiers only from those supplied by the operator, and include every operator-required verification. Explain rollback in concrete terms."
        ),
        output_type=ImplementationPlanOutput,
    )
    generator = Agent(
        name="Code Generation Agent",
        model=model_name,
        instructions=shared + (
            "Generate complete UTF-8 text for each create or update. For every update or delete, copy the exact sha256 from the supplied repository snapshot into expected_sha256. "
            "Never use partial patches or ellipses. Do not touch files outside the implementation design. Keep the change set minimal and internally consistent."
        ),
        output_type=ChangeSetOutput,
    )
    code_review = Agent(
        name="Code Review Agent",
        model=model_name,
        instructions=shared + (
            "Review the implemented staging change set and verification results for correctness, maintainability, contract drift, hidden coupling, error handling, and rollback risk. "
            "Block when the implementation does not satisfy the authorized packet or when a material correctness issue remains."
        ),
        output_type=ImplementationReviewOutput,
    )
    security_review = Agent(
        name="Implementation Security Review Agent",
        model=model_name,
        instructions=shared + (
            "Review the staging changes for privilege expansion, authentication or authorization defects, unsafe agent permissions, secret exposure, injection paths, unsafe deserialization, destructive actions, and missing audit controls. "
            "Block any material security issue or any change that exceeds the authority in the authorized release packet."
        ),
        output_type=ImplementationReviewOutput,
    )
    quality_review = Agent(
        name="Implementation Quality Review Agent",
        model=model_name,
        instructions=shared + (
            "Review whether the registered verification results cover the authorized behavior, regression risk, failure paths, accessibility where relevant, and agent boundary tests where relevant. "
            "Block when a failed verification exists or when a critical behavior lacks credible verification evidence."
        ),
        output_type=ImplementationReviewOutput,
    )
    return ImplementationAgentSet(planner, generator, code_review, security_review, quality_review)


class OpenAIImplementationProvider:
    def __init__(self, agents: ImplementationAgentSet | None = None, runner: RunnerLike | None = None, *, max_turns: int = 10) -> None:
        self.agents = agents or build_implementation_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def normalize(request: dict[str, Any]) -> dict[str, Any]:
        release = request.get("release_record")
        if not isinstance(release, dict) or release.get("status") != "authorized_for_implementation":
            raise ValueError("implementation requires an authorized product release record")
        context_paths = request.get("context_paths")
        allowed_verifications = request.get("allowed_verification_ids")
        required_verifications = request.get("required_verification_ids", [])
        if not isinstance(context_paths, list) or not context_paths:
            raise ValueError("implementation requires explicit repository context paths")
        if not isinstance(allowed_verifications, list) or not allowed_verifications:
            raise ValueError("implementation requires registered verification identifiers")
        if not set(required_verifications).issubset(set(allowed_verifications)):
            raise ValueError("required verification identifiers must be operator-allowed")
        normalized = dict(request)
        normalized["market"] = "Canada"
        return normalized

    def _run(self, agent: Any, task: str, payload: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, payload), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def plan_changes(self, request: dict[str, Any], repository_context: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(
            self.agents.planner,
            "Design the reversible staging implementation.",
            {
                "request": request,
                "repository_context": repository_context,
                "allowed_verification_ids": request["allowed_verification_ids"],
                "required_verification_ids": request.get("required_verification_ids", []),
            },
            ImplementationPlanOutput,
        )

    def generate_changes(self, request: dict[str, Any], repository_context: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.generator,
            "Generate the complete staging file change set.",
            {"request": request, "repository_context": repository_context, "implementation_design": plan},
            ChangeSetOutput,
        )

    def review_code(self, request: dict[str, Any], plan: dict[str, Any], applied_changes: list[dict[str, Any]], verification: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(
            self.agents.code_review,
            "Review staging implementation correctness.",
            {"request": request, "design": plan, "applied_changes": applied_changes, "verification": verification},
            ImplementationReviewOutput,
        )

    def review_security(self, request: dict[str, Any], plan: dict[str, Any], applied_changes: list[dict[str, Any]], verification: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(
            self.agents.security_review,
            "Review staging implementation security and authority boundaries.",
            {"request": request, "design": plan, "applied_changes": applied_changes, "verification": verification},
            ImplementationReviewOutput,
        )

    def review_quality(self, request: dict[str, Any], applied_changes: list[dict[str, Any]], verification: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run(
            self.agents.quality_review,
            "Review staging verification coverage and release quality.",
            {"request": request, "applied_changes": applied_changes, "verification": verification},
            ImplementationReviewOutput,
        )
