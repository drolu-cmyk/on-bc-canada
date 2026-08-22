#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "runtime-observability.template.json"


def fail(errors: list[str]) -> int:
    print("Runtime observability validation failed:", file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    return 1


def main() -> int:
    errors: list[str] = []
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    resources = template.get("Resources", {})
    parameters = template.get("Parameters", {})

    required = {
        "RuntimeTelemetryKey": "AWS::KMS::Key",
        "RuntimeTelemetryLogGroup": "AWS::Logs::LogGroup",
        "RuntimeTelemetryLogStream": "AWS::Logs::LogStream",
        "RuntimeTelemetryPublisherPolicy": "AWS::IAM::ManagedPolicy",
        "RuntimeAssuranceReaderPolicy": "AWS::IAM::ManagedPolicy",
        "RuntimeAlarmTopic": "AWS::SNS::Topic",
        "RuntimeModelErrorAlarm": "AWS::CloudWatch::Alarm",
        "RuntimeDailyTokenAlarm": "AWS::CloudWatch::Alarm",
        "RuntimeDailyEstimatedCostAlarm": "AWS::CloudWatch::Alarm",
        "RuntimeLatencyAlarm": "AWS::CloudWatch::Alarm",
        "RuntimeObservabilityDashboard": "AWS::CloudWatch::Dashboard",
    }
    for name, resource_type in required.items():
        if resources.get(name, {}).get("Type") != resource_type:
            errors.append(f"missing {name}={resource_type}")

    if parameters.get("RetentionDays", {}).get("Default") != 30:
        errors.append("pilot telemetry retention must default to 30 days")
    if parameters.get("DailyEstimatedCostThresholdUSD", {}).get("Default") != 5:
        errors.append("pilot estimated model cost alarm must default to USD 5 per day")
    if parameters.get("DailyTokenThreshold", {}).get("Default") != 1000000:
        errors.append("pilot token alarm must default to 1,000,000 tokens per day")

    key = resources.get("RuntimeTelemetryKey", {})
    if key.get("DeletionPolicy") != "Retain" or key.get("Properties", {}).get("EnableKeyRotation") is not True:
        errors.append("runtime telemetry KMS key must be retained with rotation enabled")

    log_group = resources.get("RuntimeTelemetryLogGroup", {})
    props = log_group.get("Properties", {})
    if log_group.get("DeletionPolicy") != "Retain":
        errors.append("runtime telemetry log group must retain resource ownership on stack deletion")
    if props.get("RetentionInDays") != {"Ref": "RetentionDays"}:
        errors.append("runtime telemetry log group must use the bounded retention parameter")
    if props.get("KmsKeyId") != {"Fn::GetAtt": ["RuntimeTelemetryKey", "Arn"]}:
        errors.append("runtime telemetry log group must use the dedicated KMS key")

    publisher_statements = (
        resources.get("RuntimeTelemetryPublisherPolicy", {})
        .get("Properties", {})
        .get("PolicyDocument", {})
        .get("Statement", [])
    )
    if len(publisher_statements) != 1:
        errors.append("publisher policy must contain exactly one statement")
    elif publisher_statements[0].get("Action") != "logs:PutLogEvents":
        errors.append("publisher policy may grant only logs:PutLogEvents")

    reader_statements = (
        resources.get("RuntimeAssuranceReaderPolicy", {})
        .get("Properties", {})
        .get("PolicyDocument", {})
        .get("Statement", [])
    )
    reader_actions: set[str] = set()
    for statement in reader_statements:
        actions = statement.get("Action", [])
        if isinstance(actions, str):
            reader_actions.add(actions)
        else:
            reader_actions.update(actions)
    if reader_actions != {"logs:StartQuery", "logs:GetQueryResults", "logs:StopQuery"}:
        errors.append("Runtime Assurance reader policy must be query-only")

    for alarm_name in (
        "RuntimeModelErrorAlarm",
        "RuntimeDailyTokenAlarm",
        "RuntimeDailyEstimatedCostAlarm",
        "RuntimeLatencyAlarm",
    ):
        alarm = resources.get(alarm_name, {}).get("Properties", {})
        dimensions = alarm.get("Dimensions")
        if dimensions != [{"Name": "Environment", "Value": {"Ref": "EnvironmentName"}}]:
            errors.append(f"{alarm_name} must use Environment as its only metric dimension")
        if alarm.get("TreatMissingData") != "notBreaching":
            errors.append(f"{alarm_name} must not interpret missing telemetry as a breach")

    serialized = json.dumps(template, sort_keys=True).casefold()
    for prohibited in (
        "logs:createloggroup",
        "logs:createlogstream",
        "secretsmanager:",
        "learner_id",
        "submission_id",
        "tool_output",
        "tool_argument",
        "model_output",
        "prompt_body",
    ):
        if prohibited in serialized:
            errors.append(f"observability template contains prohibited capability or payload field: {prohibited}")

    runtime_source = (ROOT / "runtime" / "aws_runtime_observability.py").read_text(encoding="utf-8")
    for required_text in (
        "CloudWatchTelemetryPublisher",
        "CloudWatchRuntimeTelemetrySource",
        "dedup trace_id",
        '"Dimensions": [["Environment"]]',
        "validate_cloudwatch_event",
    ):
        if required_text not in runtime_source:
            errors.append(f"AWS runtime observability source missing contract: {required_text}")

    if errors:
        return fail(errors)
    print("Runtime observability validation passed for KMS, retention, least privilege, bounded metrics and Runtime Assurance query access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
