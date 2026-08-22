from __future__ import annotations

import unittest

from runtime.employer_workforce_context import AggregateMetric, EmployerWorkforceRequest, WorkTask


def employer_request() -> EmployerWorkforceRequest:
    return EmployerWorkforceRequest(
        organization_ref="org-canada-001",
        sector="Nonprofit services",
        workflow_name="Community intake triage",
        workflow_purpose="Classify incoming service requests and route them to the appropriate internal service queue for human follow-up.",
        tasks=(
            WorkTask(
                task_id="review-intake",
                description="Review each incoming request and identify the service category and routing destination.",
                role_labels=("Intake Coordinator",),
                current_tools=("Shared mailbox", "Case management system"),
                pain_points=("Repeated manual classification", "Inconsistent category labels"),
            ),
            WorkTask(
                task_id="route-request",
                description="Route the classified request to the correct queue and preserve a record for staff review.",
                role_labels=("Intake Coordinator", "Program Manager"),
                current_tools=("Case management system",),
                pain_points=("Rework when routing information is incomplete",),
            ),
        ),
        constraints=("Licensed or accountable staff retain final decisions", "No production personal data in the first pilot"),
        baseline_metrics=(
            AggregateMetric(
                metric_id="monthly-volume",
                description="Average number of intake requests received per month",
                value=2400,
                unit="requests/month",
            ),
        ),
        desired_outcomes=("Reduce repetitive classification work", "Improve routing consistency"),
        data_classification="confidential",
    )


class EmployerWorkforceContextTests(unittest.TestCase):
    def test_model_payload_excludes_local_organization_reference(self):
        request = employer_request()
        payload = request.as_model_payload()
        self.assertNotIn("organization_ref", payload)
        self.assertEqual("Community intake triage", payload["workflow_name"])
        self.assertEqual({"Intake Coordinator", "Program Manager"}, set(payload["role_labels"]))
        self.assertTrue(payload["boundary"]["no_employee_ranking"])

    def test_obvious_personal_contact_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "personal email"):
            EmployerWorkforceRequest(
                organization_ref="org-canada-002",
                sector="Services",
                workflow_name="Support review",
                workflow_purpose="Review service requests from jane@example.com and route them for follow-up.",
                tasks=(
                    WorkTask(
                        task_id="review-support",
                        description="Review organization-level support requests and route them to a service queue.",
                        role_labels=("Support Analyst",),
                    ),
                ),
            )

    def test_duplicate_task_ids_fail_closed(self):
        task = WorkTask(
            task_id="review-item",
            description="Review an organization-level work item and determine the next process step.",
            role_labels=("Analyst",),
        )
        with self.assertRaisesRegex(ValueError, "task IDs must be unique"):
            EmployerWorkforceRequest(
                organization_ref="org-canada-003",
                sector="Services",
                workflow_name="Item review",
                workflow_purpose="Review incoming work items and determine the next internal processing step.",
                tasks=(task, task),
            )


if __name__ == "__main__":
    unittest.main()
