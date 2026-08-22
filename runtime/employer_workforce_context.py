"""Organization-level input contract for the Employer Workforce Graph.

The graph accepts workflow, task, constraint, and aggregate metric information.
It is not an employee-performance or hiring data model. Organization references
are retained locally but excluded from model context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,79}$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?:\+?1[-. ]?)?(?:\(?\d{3}\)?[-. ]?)\d{3}[-. ]?\d{4}")


def _clean(value: str) -> str:
    return " ".join(value.split())


def _reject_obvious_personal_contact(value: str) -> None:
    if _EMAIL.search(value) or _PHONE.search(value):
        raise ValueError("Employer Workforce inputs must not contain personal email addresses or phone numbers")


@dataclass(frozen=True)
class WorkTask:
    task_id: str
    description: str
    role_labels: tuple[str, ...]
    current_tools: tuple[str, ...] = ()
    pain_points: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.task_id):
            raise ValueError("task ID must be a stable lowercase identifier")
        if len(_clean(self.description)) < 15:
            raise ValueError("task description must describe organization-level work")
        if not self.role_labels:
            raise ValueError("task requires at least one role label")
        for value in (self.description, *self.role_labels, *self.current_tools, *self.pain_points):
            _reject_obvious_personal_contact(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": _clean(self.description),
            "role_labels": list(self.role_labels),
            "current_tools": list(self.current_tools),
            "pain_points": list(self.pain_points),
        }


@dataclass(frozen=True)
class AggregateMetric:
    metric_id: str
    description: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.metric_id):
            raise ValueError("metric ID must be a stable lowercase identifier")
        if len(_clean(self.description)) < 8 or not _clean(self.unit):
            raise ValueError("aggregate metric requires a description and unit")
        _reject_obvious_personal_contact(self.description)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "description": _clean(self.description),
            "value": float(self.value),
            "unit": _clean(self.unit),
        }


@dataclass(frozen=True)
class EmployerWorkforceRequest:
    organization_ref: str
    sector: str
    workflow_name: str
    workflow_purpose: str
    tasks: tuple[WorkTask, ...]
    constraints: tuple[str, ...] = ()
    baseline_metrics: tuple[AggregateMetric, ...] = ()
    desired_outcomes: tuple[str, ...] = ()
    data_classification: Literal["operational", "confidential"] = "operational"

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.organization_ref):
            raise ValueError("organization reference must be a pseudonymous stable identifier")
        if len(_clean(self.sector)) < 2:
            raise ValueError("sector is required")
        if len(_clean(self.workflow_name)) < 3:
            raise ValueError("workflow name is required")
        if len(_clean(self.workflow_purpose)) < 15:
            raise ValueError("workflow purpose must be specific")
        if not self.tasks:
            raise ValueError("at least one organization-level task is required")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("task IDs must be unique")
        if len({metric.metric_id for metric in self.baseline_metrics}) != len(self.baseline_metrics):
            raise ValueError("metric IDs must be unique")
        for value in (self.sector, self.workflow_name, self.workflow_purpose, *self.constraints, *self.desired_outcomes):
            _reject_obvious_personal_contact(value)

    @property
    def role_labels(self) -> tuple[str, ...]:
        return tuple(sorted({role for task in self.tasks for role in task.role_labels}, key=str.casefold))

    def as_model_payload(self) -> dict[str, Any]:
        """Return organization context without the local organization reference."""
        return {
            "sector": _clean(self.sector),
            "workflow_name": _clean(self.workflow_name),
            "workflow_purpose": _clean(self.workflow_purpose),
            "tasks": [task.as_dict() for task in self.tasks],
            "role_labels": list(self.role_labels),
            "constraints": list(self.constraints),
            "baseline_metrics": [metric.as_dict() for metric in self.baseline_metrics],
            "desired_outcomes": list(self.desired_outcomes),
            "data_classification": self.data_classification,
            "boundary": {
                "organization_level_only": True,
                "no_employee_ranking": True,
                "no_hiring_or_termination_decision": True,
                "no_individual_performance_decision": True,
                "no_automatic_work_intelligence_write": True,
            },
        }

    def as_local_record(self) -> dict[str, Any]:
        return {"organization_ref": self.organization_ref, **self.as_model_payload()}
