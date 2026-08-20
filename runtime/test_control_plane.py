from __future__ import annotations

import unittest

from control_plane import EnrollmentControlPlane


class ControlPlaneTests(unittest.TestCase):
    def test_duplicate_submission_is_idempotent(self) -> None:
        control_plane = EnrollmentControlPlane()
        first = control_plane.submit_enrollment(
            submission_id="submission-001",
            learner_ref="learner-pseudo-001",
            cohort_id="cohort-2026-01",
            consented=True,
            seats_remaining=3,
        )
        second = control_plane.submit_enrollment(
            submission_id="submission-001",
            learner_ref="learner-pseudo-001",
            cohort_id="cohort-2026-01",
            consented=True,
            seats_remaining=3,
        )
        self.assertEqual(len(first), 4)
        self.assertEqual(second, [])
        self.assertEqual(len(control_plane.ledger.events), 4)

    def test_capacity_and_consent_route_to_safe_states(self) -> None:
        control_plane = EnrollmentControlPlane()
        waitlisted = control_plane.submit_enrollment(
            submission_id="submission-002",
            learner_ref="learner-pseudo-002",
            cohort_id="cohort-2026-01",
            consented=True,
            seats_remaining=0,
        )
        review = control_plane.submit_enrollment(
            submission_id="submission-003",
            learner_ref="learner-pseudo-003",
            cohort_id="cohort-2026-01",
            consented=False,
            seats_remaining=3,
        )
        self.assertEqual(waitlisted[-1]["event_type"], "learner.waitlisted.v1")
        self.assertEqual(review[-1]["event_type"], "human-review.requested.v1")

    def test_events_are_hashed_and_do_not_contain_email_fields(self) -> None:
        control_plane = EnrollmentControlPlane()
        control_plane.submit_enrollment(
            submission_id="submission-004",
            learner_ref="learner-pseudo-004",
            cohort_id="cohort-2026-01",
            consented=True,
            seats_remaining=1,
        )
        for event in control_plane.ledger.events:
            self.assertIn("event_hash", event["integrity"])
            self.assertNotIn("email", event["payload"])

    def test_consent_and_attendance_records_are_idempotent(self) -> None:
        control_plane = EnrollmentControlPlane()
        consent = control_plane.record_consent(
            consent_id="consent-001",
            learner_ref="learner-pseudo-005",
            cohort_id="cohort-2026-01",
            purposes=["attendance", "enrollment", "attendance"],
            status="granted",
            policy_version="privacy-0.1.0",
            evidence_ref="evidence:consent-001",
        )
        attendance = control_plane.record_attendance(
            attendance_id="attendance-001",
            learner_ref="learner-pseudo-005",
            cohort_id="cohort-2026-01",
            session_id="session-001",
            status="present",
            source="virtual_session",
            policy_version="attendance-0.1.0",
            evidence_ref="evidence:attendance-001",
        )
        duplicate = control_plane.record_attendance(
            attendance_id="attendance-001",
            learner_ref="learner-pseudo-005",
            cohort_id="cohort-2026-01",
            session_id="session-001",
            status="present",
            source="virtual_session",
            policy_version="attendance-0.1.0",
            evidence_ref="evidence:attendance-001",
        )
        self.assertEqual(consent["payload"]["purposes"], ["attendance", "enrollment"])
        self.assertEqual(attendance["event_type"], "attendance.recorded.v1")
        self.assertEqual(duplicate["event_id"], attendance["event_id"])
        self.assertEqual(len(control_plane.ledger.events), 2)

    def test_sensitive_support_routes_to_human_review(self) -> None:
        control_plane = EnrollmentControlPlane()
        events = control_plane.request_support(
            support_id="support-001",
            learner_ref="learner-pseudo-006",
            cohort_id="cohort-2026-01",
            category="accessibility",
            priority="routine",
            evidence_ref="evidence:support-001",
        )
        self.assertEqual([event["event_type"] for event in events], [
            "support.requested.v1",
            "human-review.requested.v1",
        ])
        self.assertEqual(events[-1]["payload"]["reason_code"], "accessibility_authorization_required")


if __name__ == "__main__":
    unittest.main()
