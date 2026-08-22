#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${DURABLE_EXECUTION_STACK_NAME:=sozorock-ca-durable-execution}"
: "${DURABLE_EXECUTION_ENVIRONMENT:=pilot}"
: "${DURABLE_EXECUTION_TABLE_NAME:=sozorock-ca-graph-executions}"
: "${DURABLE_EXECUTION_ALARM_EMAIL:=}"

if [[ "$AWS_REGION" != "ca-central-1" ]]; then
  echo "Durable execution must deploy in ca-central-1." >&2
  exit 1
fi

actual="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$actual" != "$AWS_ACCOUNT_ID" ]]; then
  echo "AWS account mismatch." >&2
  exit 1
fi

python scripts/validate_durable_execution.py

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$DURABLE_EXECUTION_STACK_NAME" \
  --template-file infra/durable-execution.template.json \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "EnvironmentName=$DURABLE_EXECUTION_ENVIRONMENT" \
    "ExecutionTableName=$DURABLE_EXECUTION_TABLE_NAME" \
    "AlarmEmail=$DURABLE_EXECUTION_ALARM_EMAIL"

out() {
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$DURABLE_EXECUTION_STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

printf 'Durable execution stack ready.\n'
printf 'Table: %s\n' "$(out ExecutionTableName)"
printf 'Work queue: %s\n' "$(out WorkQueueUrl)"
printf 'Event bus: %s\n' "$(out PlatformEventBusName)"
printf 'State policy: %s\n' "$(out ExecutionStatePolicyArn)"
printf 'Producer policy: %s\n' "$(out WorkProducerPolicyArn)"
printf 'Consumer policy: %s\n' "$(out WorkConsumerPolicyArn)"
