#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${RUNTIME_OBSERVABILITY_STACK_NAME:=sozorock-ca-runtime-observability}"
: "${RUNTIME_OBSERVABILITY_ENVIRONMENT:=pilot}"
: "${RUNTIME_OBSERVABILITY_RETENTION_DAYS:=30}"
: "${RUNTIME_OBSERVABILITY_ALARM_EMAIL:=}"
: "${RUNTIME_DAILY_TOKEN_THRESHOLD:=1000000}"
: "${RUNTIME_DAILY_ESTIMATED_COST_THRESHOLD_USD:=5}"
: "${RUNTIME_AVERAGE_LATENCY_THRESHOLD_MS:=30000}"

actual="$(aws sts get-caller-identity --query Account --output text)"
[[ "$actual" == "$AWS_ACCOUNT_ID" ]] || { echo "AWS account mismatch." >&2; exit 1; }
[[ "$AWS_REGION" == "ca-central-1" ]] || { echo "Runtime observability must deploy in ca-central-1." >&2; exit 1; }

python scripts/validate_runtime_observability.py

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$RUNTIME_OBSERVABILITY_STACK_NAME" \
  --template-file infra/runtime-observability.template.json \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "EnvironmentName=$RUNTIME_OBSERVABILITY_ENVIRONMENT" \
    "RetentionDays=$RUNTIME_OBSERVABILITY_RETENTION_DAYS" \
    "AlarmEmail=$RUNTIME_OBSERVABILITY_ALARM_EMAIL" \
    "DailyTokenThreshold=$RUNTIME_DAILY_TOKEN_THRESHOLD" \
    "DailyEstimatedCostThresholdUSD=$RUNTIME_DAILY_ESTIMATED_COST_THRESHOLD_USD" \
    "AverageRunLatencyThresholdMs=$RUNTIME_AVERAGE_LATENCY_THRESHOLD_MS"

out() {
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$RUNTIME_OBSERVABILITY_STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

log_group="$(out TelemetryLogGroupName)"
log_stream="$(out TelemetryLogStreamName)"
publisher_policy="$(out PublisherPolicyArn)"
reader_policy="$(out RuntimeAssuranceReaderPolicyArn)"
dashboard="$(out DashboardName)"

cat <<EOF
Runtime observability stack is ready.
Region: $AWS_REGION
Log group: $log_group
Log stream: $log_stream
Publisher policy ARN: $publisher_policy
Runtime Assurance reader policy ARN: $reader_policy
Dashboard: $dashboard

Attach the publisher policy only to the governed model runtime workload role.
Attach the reader policy only to the Runtime Assurance workload role.
Then enable centralized publishing in the runtime environment with:
SOZOROCK_AWS_OBSERVABILITY_ENABLED=1
SOZOROCK_AWS_OBSERVABILITY_REGION=$AWS_REGION
SOZOROCK_AWS_TELEMETRY_LOG_GROUP=$log_group
SOZOROCK_AWS_TELEMETRY_LOG_STREAM=$log_stream
SOZOROCK_AWS_OBSERVABILITY_ENVIRONMENT=$RUNTIME_OBSERVABILITY_ENVIRONMENT
EOF
