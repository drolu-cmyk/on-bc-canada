#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${DOMAIN_DATA_STACK_NAME:=sozorock-ca-domain-data}"
: "${DOMAIN_DATA_ENVIRONMENT:=pilot}"
: "${DOMAIN_DATA_CLUSTER_IDENTIFIER:=sozorock-ca-domain-data}"
: "${DOMAIN_DATA_DATABASE:=sozorockcanada}"
: "${DOMAIN_DATA_ENGINE_VERSION:=16.8}"

if [[ "$AWS_REGION" != "ca-central-1" ]]; then
  echo "Domain data must deploy in ca-central-1." >&2
  exit 1
fi

actual="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$actual" != "$AWS_ACCOUNT_ID" ]]; then
  echo "AWS account mismatch." >&2
  exit 1
fi

python scripts/validate_domain_data.py

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$DOMAIN_DATA_STACK_NAME" \
  --template-file infra/domain-data.template.json \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "EnvironmentName=$DOMAIN_DATA_ENVIRONMENT" \
    "ClusterIdentifier=$DOMAIN_DATA_CLUSTER_IDENTIFIER" \
    "DatabaseName=$DOMAIN_DATA_DATABASE" \
    "EngineVersion=$DOMAIN_DATA_ENGINE_VERSION"

out() {
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$DOMAIN_DATA_STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

printf 'Domain data infrastructure ready.\n'
printf 'Cluster ARN: %s\n' "$(out DomainClusterArn)"
printf 'Database: %s\n' "$(out DomainDatabaseName)"
printf 'Master secret ARN: %s\n' "$(out MasterUserSecretArn)"
printf 'Intelligence secret ARN: %s\n' "$(out IntelligenceRuntimeSecretArn)"
printf 'Learning secret ARN: %s\n' "$(out LearningRuntimeSecretArn)"
printf 'Migration policy: %s\n' "$(out DomainMigrationPolicyArn)"
printf 'Intelligence policy: %s\n' "$(out IntelligenceDataApiPolicyArn)"
printf 'Learning policy: %s\n' "$(out LearningDataApiPolicyArn)"
