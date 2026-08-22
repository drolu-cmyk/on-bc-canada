#!/usr/bin/env bash
set -euo pipefail
: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${ENGAGEMENT_STACK_NAME:=sozorock-ca-engagement}"
: "${ADMIN_EMAIL:=oluview@gmail.com}"
: "${NOTIFICATION_EMAIL:=oluview@gmail.com}"
actual="$(aws sts get-caller-identity --query Account --output text)"
[[ "$actual" == "$AWS_ACCOUNT_ID" ]] || { echo "AWS account mismatch." >&2; exit 1; }
aws cloudformation deploy --region "$AWS_REGION" --stack-name "$ENGAGEMENT_STACK_NAME" --template-file infra/engagement-backend.template.json --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset --parameter-overrides "AdminEmail=$ADMIN_EMAIL" "NotificationEmail=$NOTIFICATION_EMAIL" "AllowedOrigin=https://canada.sozorock.com"
out(){ aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$ENGAGEMENT_STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
api="$(out ApiEndpoint)"; client="$(out AdminClientId)"; domain="$(out AdminDomain)"; pool="$(out AdminUserPoolId)"
cat > site/engagement-config.js <<EOF
window.SOZOROCK_ENGAGEMENT={apiEndpoint:"$api",adminClientId:"$client",adminDomain:"$domain",adminUserPoolId:"$pool",redirectUri:"https://canada.sozorock.com/admin"};
EOF
printf 'Engagement backend ready: %s\n' "$api"
