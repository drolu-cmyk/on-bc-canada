#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "durable-execution.template.json"
WORKFLOW = ROOT / ".github" / "workflows" / "durable-execution-deploy.yml"
SCRIPT = ROOT / "scripts" / "deploy_durable_execution.sh"


def main() -> int:
    errors: list[str] = []
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    resources = template.get("Resources", {})

    table = resources.get("ExecutionTable", {})
    props = table.get("Properties", {})
    if table.get("Type") != "AWS::DynamoDB::Table":
        errors.append("ExecutionTable must be AWS::DynamoDB::Table")
    if props.get("BillingMode") != "PAY_PER_REQUEST":
        errors.append("ExecutionTable must use PAY_PER_REQUEST")
    if props.get("DeletionProtectionEnabled") is not True:
        errors.append("ExecutionTable deletion protection must be enabled")
    pitr = props.get("PointInTimeRecoverySpecification", {})
    if pitr.get("PointInTimeRecoveryEnabled") is not True or pitr.get("RecoveryPeriodInDays") != 35:
        errors.append("ExecutionTable must retain 35-day point-in-time recovery")
    sse = props.get("SSESpecification", {})
    if sse.get("SSEEnabled") is not True or sse.get("SSEType") != "KMS" or not sse.get("KMSMasterKeyId"):
        errors.append("ExecutionTable must use KMS server-side encryption")
    ttl = props.get("TimeToLiveSpecification", {})
    if ttl != {"AttributeName": "expires_at_epoch", "Enabled": True}:
        errors.append("ExecutionTable TTL must be limited to expires_at_epoch")
    indexes = {item.get("IndexName"): item for item in props.get("GlobalSecondaryIndexes", [])}
    index = indexes.get("ExecutionUpdatedIndex", {})
    schema = index.get("KeySchema", [])
    if schema != [
        {"AttributeName": "sk", "KeyType": "HASH"},
        {"AttributeName": "updated_at", "KeyType": "RANGE"},
    ]:
        errors.append("ExecutionUpdatedIndex must query STATE records by updated_at")

    for name in ("WorkQueue", "WorkDeadLetterQueue"):
        queue = resources.get(name, {})
        qprops = queue.get("Properties", {})
        if queue.get("Type") != "AWS::SQS::Queue":
            errors.append(f"{name} must be AWS::SQS::Queue")
            continue
        if qprops.get("FifoQueue") is not True or qprops.get("ContentBasedDeduplication") is not False:
            errors.append(f"{name} must be explicit-dedup FIFO")
        if qprops.get("ReceiveMessageWaitTimeSeconds") != 20:
            errors.append(f"{name} must use 20-second long polling")
        if qprops.get("MessageRetentionPeriod") != 1209600:
            errors.append(f"{name} must retain messages for 14 days")
        if not qprops.get("KmsMasterKeyId"):
            errors.append(f"{name} must use KMS encryption")

    work_props = resources.get("WorkQueue", {}).get("Properties", {})
    redrive = work_props.get("RedrivePolicy", {})
    if "deadLetterTargetArn" not in redrive or redrive.get("maxReceiveCount") != {"Ref": "MaxReceiveCount"}:
        errors.append("WorkQueue must redrive to the retained DLQ")
    if work_props.get("VisibilityTimeout") != 120:
        errors.append("WorkQueue visibility timeout must default to 120 seconds")

    if resources.get("PlatformEventBus", {}).get("Type") != "AWS::Events::EventBus":
        errors.append("PlatformEventBus is required")

    forbidden_types = {"AWS::Lambda::Function", "AWS::StepFunctions::StateMachine", "AWS::ECS::Service"}
    for name, resource in resources.items():
        if resource.get("Type") in forbidden_types:
            errors.append(f"durable execution source must not auto-deploy a worker: {name}")

    for policy_name in ("DurableExecutionStatePolicy", "DurableWorkProducerPolicy", "DurableWorkConsumerPolicy"):
        policy = resources.get(policy_name, {})
        if policy.get("Type") != "AWS::IAM::ManagedPolicy":
            errors.append(f"missing managed policy: {policy_name}")
            continue
        statements = policy.get("Properties", {}).get("PolicyDocument", {}).get("Statement", [])
        for statement in statements:
            actions = statement.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if any(action in {"dynamodb:Scan", "sqs:PurgeQueue", "kms:*", "iam:PassRole"} for action in actions):
                errors.append(f"{policy_name} grants a forbidden broad action")

    for alarm in ("DeadLetterQueueAlarm", "WorkQueueAgeAlarm"):
        if resources.get(alarm, {}).get("Type") != "AWS::CloudWatch::Alarm":
            errors.append(f"missing durable execution alarm: {alarm}")

    workflow_text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""
    if "workflow_dispatch:" not in workflow_text:
        errors.append("durable execution deployment must be workflow_dispatch only")
    if "\n  push:" in workflow_text or "\n  pull_request:" in workflow_text:
        errors.append("durable execution deployment must not run on push or pull request")
    if "DURABLE_EXECUTION_DEPLOYMENT_ENABLED" not in workflow_text:
        errors.append("durable execution deployment requires an explicit repository gate")
    if "DURABLE_EXECUTION_DEPLOY_ROLE_ARN" not in workflow_text:
        errors.append("durable execution deployment requires a dedicated OIDC role variable")

    script_text = SCRIPT.read_text(encoding="utf-8") if SCRIPT.exists() else ""
    if "ca-central-1" not in script_text or "aws sts get-caller-identity" not in script_text:
        errors.append("durable execution deploy script must verify account and Canada region")

    if errors:
        print("Durable execution validation failed:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Durable execution validation passed for encrypted state, FIFO delivery, DLQ, and manual deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
