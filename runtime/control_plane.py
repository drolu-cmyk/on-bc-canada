"""Provider-neutral enrollment-to-onboarding control-plane slice.

This module is a local contract reference for AWS implementations. It uses
immutable event dictionaries and an idempotency index so the same behavior can
be exercised without cloud credentials or learner data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class EventLedger:
    """An append-only local ledger with idempotency and a hash chain."""

    events: list[dict[str, Any]] = field(default_factory=list)
    idempotency_keys: dict[str, str] = field(default_factory=dict)

    def append(
        self,
        *,
        event_type: str,
        program_id: str,
        producer: str,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        privacy_class: str = "learner_private",
        retention_class: str = "cohort_lifecycle",
        learner_id: str | None = None,
        cohort_id: str | None = None,
        causation_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        existing_event_id = self.idempotency_keys.get(idempotency_key)
        if existing_event_id:
            return next(event for event in self.events if event["event_id"] == existing_event_id)

        previous_hash = self.events[-1].get("integrity", {}).get("event_hash") if self.events else None
        event_id = f"evt-{len(self.events) + 1:06d}"
        event: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "program_id": program_id,
            "schema_version": "1.0",
            "producer": producer,
            "actor": {"type": "automation", "id": actor_id},
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "payload": payload,
            "privacy_class": privacy_class,
            "retention_class": retention_class,
            "region": "ca-central-1",
            "policy_version": "launch-0.1.0",
        }
        if learner_id:
            event["learner_id"] = learner_id
        if cohort_id:
            event["cohort_id"] = cohort_id
        if causation_id:
            event["causation_id"] = causation_id
        if previous_hash:
            event["integrity"] = {"previous_event_hash": previous_hash}
        event_hash = hashlib.sha256(_canonical(event)).hexdigest()
        event.setdefault("integrity", {})["event_hash"] = event_hash
        self.events.append(event)
        self.idempotency_keys[idempotency_key] = event_id
        return event


class EnrollmentControlPlane:
    """Automate the standard enrollment path while routing exceptions."""

    def __init__(self, program_id: str = "applied-ai-training-canada", ledger: EventLedger | None = None) -> None:
        self.program_id = program_id
        self.ledger = ledger or EventLedger()

    def submit_enrollment(
        self,
        *,
        submission_id: str,
        learner_ref: str,
        cohort_id: str,
        consented: bool,
        seats_remaining: int,
        occurred_at: str = "2026-01-01T00:00:00Z",
    ) -> list[dict[str, Any]]:
        """Return newly created events; a replay returns the original events."""

        correlation_id = f"corr-{submission_id}"
        start = len(self.ledger.events)
        submitted = self.ledger.append(
            event_type="enrollment.submitted.v1",
            program_id=self.program_id,
            producer="enrollment",
            actor_id="enrollment-automation",
            correlation_id=correlation_id,
            idempotency_key=f"form:{submission_id}:submitted",
            payload={"learner_ref": learner_ref, "submission_ref": submission_id},
            learner_id=learner_ref,
            cohort_id=cohort_id,
            occurred_at=occurred_at,
        )
        if len(self.ledger.events) == start:
            return self.ledger.events[start:]

        validation = self.ledger.append(
            event_type="enrollment.validated.v1",
            program_id=self.program_id,
            producer="enrollment",
            actor_id="enrollment-automation",
            correlation_id=correlation_id,
            causation_id=submitted["event_id"],
            idempotency_key=f"form:{submission_id}:validated",
            payload={"consent_present": consented, "capacity_available": seats_remaining > 0},
            learner_id=learner_ref,
            cohort_id=cohort_id,
            occurred_at=occurred_at,
        )

        if not consented:
            self.ledger.append(
                event_type="human-review.requested.v1",
                program_id=self.program_id,
                producer="enrollment",
                actor_id="enrollment-automation",
                correlation_id=correlation_id,
                causation_id=validation["event_id"],
                idempotency_key=f"form:{submission_id}:review",
                payload={"reason_code": "consent_review_required"},
                learner_id=learner_ref,
                cohort_id=cohort_id,
                occurred_at=occurred_at,
            )
        elif seats_remaining <= 0:
            self.ledger.append(
                event_type="learner.waitlisted.v1",
                program_id=self.program_id,
                producer="cohort-journey",
                actor_id="cohort-automation",
                correlation_id=correlation_id,
                causation_id=validation["event_id"],
                idempotency_key=f"form:{submission_id}:waitlist",
                payload={"reason_code": "capacity_reached"},
                learner_id=learner_ref,
                cohort_id=cohort_id,
                occurred_at=occurred_at,
            )
        else:
            accepted = self.ledger.append(
                event_type="learner.accepted.v1",
                program_id=self.program_id,
                producer="cohort-journey",
                actor_id="cohort-automation",
                correlation_id=correlation_id,
                causation_id=validation["event_id"],
                idempotency_key=f"form:{submission_id}:accepted",
                payload={"next_action": "workspace_provisioning"},
                learner_id=learner_ref,
                cohort_id=cohort_id,
                occurred_at=occurred_at,
            )
            self.ledger.append(
                event_type="workspace.provisioning_requested.v1",
                program_id=self.program_id,
                producer="workspace",
                actor_id="workspace-automation",
                correlation_id=correlation_id,
                causation_id=accepted["event_id"],
                idempotency_key=f"workspace:{learner_ref}:{cohort_id}",
                payload={"workspace_ref": f"ws:{cohort_id}:{learner_ref}"},
                learner_id=learner_ref,
                cohort_id=cohort_id,
                occurred_at=occurred_at,
            )
        return self.ledger.events[start:]

    def record_consent(
        self,
        *,
        consent_id: str,
        learner_ref: str,
        cohort_id: str,
        purposes: list[str],
        status: str,
        policy_version: str,
        evidence_ref: str,
        occurred_at: str = "2026-01-01T00:00:00Z",
    ) -> dict[str, Any]:
        """Record a consent state without placing direct identity in the event."""

        if status not in {"granted", "withdrawn", "superseded"}:
            raise ValueError("unsupported consent status")
        event_type = f"consent.{status}.v1"
        return self.ledger.append(
            event_type=event_type,
            program_id=self.program_id,
            producer="consent",
            actor_id="consent-automation",
            correlation_id=f"corr-{consent_id}",
            idempotency_key=f"consent:{consent_id}:{status}",
            payload={
                "consent_id": consent_id,
                "purposes": sorted(set(purposes)),
                "policy_version": policy_version,
                "status": status,
                "evidence_ref": evidence_ref,
            },
            privacy_class="learner_private",
            retention_class="cohort_lifecycle",
            learner_id=learner_ref,
            cohort_id=cohort_id,
            occurred_at=occurred_at,
        )

    def record_attendance(
        self,
        *,
        attendance_id: str,
        learner_ref: str,
        cohort_id: str,
        session_id: str,
        status: str,
        source: str,
        policy_version: str,
        evidence_ref: str,
        occurred_at: str = "2026-01-01T00:00:00Z",
        correction_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record attendance or an authorized correction as an idempotent event."""

        allowed_statuses = {"present", "partial", "absent", "alternate_path", "excused", "corrected"}
        allowed_sources = {"virtual_session", "alternate_path", "operator_correction", "automation"}
        if status not in allowed_statuses:
            raise ValueError("unsupported attendance status")
        if source not in allowed_sources:
            raise ValueError("unsupported attendance source")
        if status == "corrected" and not correction_reason:
            raise ValueError("correction_reason is required for corrected attendance")
        payload: dict[str, Any] = {
            "attendance_id": attendance_id,
            "session_id": session_id,
            "status": status,
            "source": source,
            "policy_version": policy_version,
            "evidence_ref": evidence_ref,
        }
        if correction_reason:
            payload["correction_reason"] = correction_reason
        return self.ledger.append(
            event_type="attendance.recorded.v1",
            program_id=self.program_id,
            producer="attendance",
            actor_id="attendance-automation",
            correlation_id=f"corr-{attendance_id}",
            idempotency_key=f"attendance:{attendance_id}",
            payload=payload,
            privacy_class="learner_private",
            retention_class="credential_record",
            learner_id=learner_ref,
            cohort_id=cohort_id,
            occurred_at=occurred_at,
        )

    def request_support(
        self,
        *,
        support_id: str,
        learner_ref: str,
        cohort_id: str,
        category: str,
        priority: str,
        evidence_ref: str,
        occurred_at: str = "2026-01-01T00:00:00Z",
    ) -> list[dict[str, Any]]:
        """Route a support request and preserve human authorization for sensitive cases."""

        categories = {"accessibility", "technical", "learning", "safety", "privacy", "withdrawal", "correction", "complaint"}
        priorities = {"routine", "urgent", "safety_critical"}
        if category not in categories:
            raise ValueError("unsupported support category")
        if priority not in priorities:
            raise ValueError("unsupported support priority")
        start = len(self.ledger.events)
        requested = self.ledger.append(
            event_type="support.requested.v1",
            program_id=self.program_id,
            producer="support",
            actor_id="support-automation",
            correlation_id=f"corr-{support_id}",
            idempotency_key=f"support:{support_id}:requested",
            payload={
                "support_id": support_id,
                "category": category,
                "priority": priority,
                "evidence_ref": evidence_ref,
            },
            privacy_class="sensitive_support" if category in {"safety", "privacy", "accessibility"} else "learner_private",
            retention_class="quality_record",
            learner_id=learner_ref,
            cohort_id=cohort_id,
            occurred_at=occurred_at,
        )
        if category in {"safety", "privacy", "accessibility"} or priority == "safety_critical":
            self.ledger.append(
                event_type="human-review.requested.v1",
                program_id=self.program_id,
                producer="support",
                actor_id="support-automation",
                correlation_id=f"corr-{support_id}",
                causation_id=requested["event_id"],
                idempotency_key=f"support:{support_id}:human-review",
                payload={"reason_code": f"{category}_authorization_required", "support_id": support_id},
                privacy_class="sensitive_support",
                retention_class="quality_record",
                learner_id=learner_ref,
                cohort_id=cohort_id,
                occurred_at=occurred_at,
            )
        return self.ledger.events[start:]
