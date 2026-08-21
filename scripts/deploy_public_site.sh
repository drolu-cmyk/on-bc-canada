#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${CERTIFICATE_REGION:=us-east-1}"
: "${DOMAIN_NAME:=www.sozorock.ca}"
: "${STACK_NAME:=sozorock-ca-public-site}"
: "${PUBLIC_SITE_BUCKET_NAME:?PUBLIC_SITE_BUCKET_NAME is required}"

command -v aws >/dev/null
command -v jq >/dev/null

actual_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${actual_account}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "AWS account mismatch: expected ${AWS_ACCOUNT_ID}, received ${actual_account}" >&2
  exit 1
fi

cleanup_failed_stack() {
  local stack_status
  local version_listing
  local version_count
  local delete_marker_count
  stack_status="$(aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || true)"
  if [[ "${stack_status}" == "ROLLBACK_COMPLETE" ]]; then
    echo "Removing the empty ROLLBACK_COMPLETE deployment stack."
    aws cloudformation delete-stack \
      --region "${AWS_REGION}" \
      --stack-name "${STACK_NAME}"
    aws cloudformation wait stack-delete-complete \
      --region "${AWS_REGION}" \
      --stack-name "${STACK_NAME}"
  elif [[ -n "${stack_status}" && "${stack_status}" != "None" ]]; then
    return
  fi

  if ! version_listing="$(aws s3api list-object-versions \
    --region "${AWS_REGION}" \
    --bucket "${PUBLIC_SITE_BUCKET_NAME}" \
    --output json 2>/dev/null)"; then
    return
  fi
  version_count="$(jq '(.Versions // []) | length' <<<"${version_listing}")"
  delete_marker_count="$(jq '(.DeleteMarkers // []) | length' <<<"${version_listing}")"
  if [[ "${version_count}" != "0" || "${delete_marker_count}" != "0" ]]; then
    echo "The retained deployment bucket is not empty; refusing to remove it." >&2
    exit 1
  fi

  echo "Removing the empty deployment bucket."
  aws s3api delete-bucket \
    --region "${AWS_REGION}" \
    --bucket "${PUBLIC_SITE_BUCKET_NAME}" \
    --expected-bucket-owner "${AWS_ACCOUNT_ID}"
}

cleanup_failed_stack

hosted_zone_id=""
ensure_hosted_zone() {
  if [[ -n "${hosted_zone_id}" ]]; then
    return
  fi
  hosted_zone_id="$(aws route53 list-hosted-zones-by-name \
    --dns-name "sozorock.ca." \
    --query "HostedZones[?Name=='sozorock.ca.'].Id | [0]" \
    --output text)"
  if [[ -z "${hosted_zone_id}" || "${hosted_zone_id}" == "None" ]]; then
    echo "Route 53 hosted zone sozorock.ca. was not found in the approved AWS account." >&2
    exit 1
  fi
  hosted_zone_id="${hosted_zone_id##*/}"
}

upsert_cname() {
  local record_name="$1"
  local record_value="$2"
  local change_batch
  local change_id
  change_batch="$(jq -cn \
    --arg name "${record_name}" \
    --arg value "${record_value}" \
    '{Changes:[{Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"CNAME",TTL:300,ResourceRecords:[{Value:$value}]}}]}')"
  change_id="$(aws route53 change-resource-record-sets \
    --hosted-zone-id "${hosted_zone_id}" \
    --change-batch "${change_batch}" \
    --query "ChangeInfo.Id" \
    --output text)"
  aws route53 wait resource-record-sets-changed --id "${change_id}"
}

ensure_certificate() {
  local certificate_arn
  local status
  local validation
  local record_name
  local record_value
  local attempt

  certificate_arn="$(aws acm list-certificates \
    --region "${CERTIFICATE_REGION}" \
    --certificate-statuses ISSUED PENDING_VALIDATION \
    --output json | jq -r --arg domain "${DOMAIN_NAME}" \
      '[.CertificateSummaryList[] | select(.DomainName == $domain)] | sort_by(.CreatedAt) | last | .CertificateArn // empty')"

  if [[ -z "${certificate_arn}" ]]; then
    certificate_arn="$(aws acm request-certificate \
      --region "${CERTIFICATE_REGION}" \
      --domain-name "${DOMAIN_NAME}" \
      --validation-method DNS \
      --query CertificateArn \
      --output text)"
  fi

  status="$(aws acm describe-certificate \
    --region "${CERTIFICATE_REGION}" \
    --certificate-arn "${certificate_arn}" \
    --query "Certificate.Status" \
    --output text)"

  if [[ "${status}" == "ISSUED" ]]; then
    printf '%s\n' "${certificate_arn}"
    return
  fi

  ensure_hosted_zone
  for attempt in $(seq 1 60); do
    validation="$(aws acm describe-certificate \
      --region "${CERTIFICATE_REGION}" \
      --certificate-arn "${certificate_arn}" \
      --output json | jq -c --arg domain "${DOMAIN_NAME}" \
        '.Certificate.DomainValidationOptions[] | select(.DomainName == $domain) | .ResourceRecord // empty')"
    if [[ -n "${validation}" && "${validation}" != "null" ]]; then
      record_name="$(jq -r '.Name' <<<"${validation}")"
      record_value="$(jq -r '.Value' <<<"${validation}")"
      if [[ -n "${record_name}" && "${record_name}" != "null" && -n "${record_value}" && "${record_value}" != "null" ]]; then
        upsert_cname "${record_name}" "${record_value}"
        break
      fi
    fi
    status="$(aws acm describe-certificate \
      --region "${CERTIFICATE_REGION}" \
      --certificate-arn "${certificate_arn}" \
      --query "Certificate.Status" \
      --output text)"
    if [[ "${status}" == "ISSUED" ]]; then
      printf '%s\n' "${certificate_arn}"
      return
    fi
    if [[ "${status}" == "FAILED" ]]; then
      echo "ACM certificate request failed: ${certificate_arn}" >&2
      exit 1
    fi
    sleep 10
  done

  for attempt in $(seq 1 60); do
    status="$(aws acm describe-certificate \
      --region "${CERTIFICATE_REGION}" \
      --certificate-arn "${certificate_arn}" \
      --query "Certificate.Status" \
      --output text)"
    if [[ "${status}" == "ISSUED" ]]; then
      printf '%s\n' "${certificate_arn}"
      return
    fi
    if [[ "${status}" == "FAILED" ]]; then
      echo "ACM certificate request failed: ${certificate_arn}" >&2
      exit 1
    fi
    sleep 10
  done

  echo "Timed out waiting for ACM certificate issuance: ${certificate_arn}" >&2
  exit 1
}

CERTIFICATE_ARN="$(ensure_certificate)"

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file infra/public-site.template.json \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "PublicSiteBucketName=${PUBLIC_SITE_BUCKET_NAME}" \
    "DomainName=${DOMAIN_NAME}" \
    "CertificateArn=${CERTIFICATE_ARN}" \
    "PriceClass=PriceClass_100"

distribution_id="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicSiteDistributionId'].OutputValue" \
  --output text)"
distribution_domain="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicSiteDomainName'].OutputValue" \
  --output text)"

if [[ -z "${distribution_id}" || "${distribution_id}" == "None" || -z "${distribution_domain}" || "${distribution_domain}" == "None" ]]; then
  echo "CloudFormation did not return the CloudFront distribution outputs." >&2
  exit 1
fi

aws s3 sync site/ "s3://${PUBLIC_SITE_BUCKET_NAME}" \
  --region "${AWS_REGION}" \
  --delete \
  --cache-control "public,max-age=300" \
  --only-show-errors

aws cloudfront wait distribution-deployed --id "${distribution_id}"
invalidation_id="$(aws cloudfront create-invalidation \
  --distribution-id "${distribution_id}" \
  --paths "/*" \
  --query "Invalidation.Id" \
  --output text)"
aws cloudfront wait invalidation-completed --distribution-id "${distribution_id}" --id "${invalidation_id}"

ensure_hosted_zone
upsert_cname "${DOMAIN_NAME}." "${distribution_domain}"

printf 'Published https://${DOMAIN_NAME}\n'
