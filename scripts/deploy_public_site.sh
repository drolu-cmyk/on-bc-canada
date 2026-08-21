#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${CERTIFICATE_REGION:=us-east-1}"
: "${DOMAIN_NAME:=www.sozorock.ca}"
: "${ROOT_DOMAIN_NAME:=sozorock.ca}"
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

stack_status="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || true)"
publish_alias="false"
if [[ -n "${stack_status}" && "${stack_status}" != "None" ]]; then
  publish_alias="$(aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Parameters[?ParameterKey=='PublishAlias'].ParameterValue | [0]" \
    --output text 2>/dev/null || true)"
  if [[ -z "${publish_alias}" || "${publish_alias}" == "None" ]]; then
    publish_alias="true"
  fi
fi

hosted_zone_id_for_name() {
  local zone_name="$1"
  aws route53 list-hosted-zones-by-name \
    --dns-name "${zone_name}" \
    --output json | jq -r --arg zone "${zone_name}" \
      '[.HostedZones[] | select(.Name == $zone and .Config.PrivateZone == false) | .Id] | first // empty'
}

is_child_zone_delegated() {
  local parent_zone_id="$1"
  local child_zone_name="$2"
  aws route53 list-resource-record-sets \
    --hosted-zone-id "${parent_zone_id}" \
    --output json | jq -e --arg name "${child_zone_name}." \
      '[.ResourceRecordSets[] | select(.Name == $name and .Type == "NS")] | length > 0' >/dev/null
}

hosted_zone_for_record() {
  local record_name="$1"
  local record_fqdn="${record_name%.}"
  local domain_fqdn="${DOMAIN_NAME%.}"
  local root_fqdn="${ROOT_DOMAIN_NAME%.}"
  local root_zone_id
  local domain_zone_id

  if [[ "${record_fqdn}" != "${root_fqdn}" && "${record_fqdn}" != *".${root_fqdn}" ]]; then
    echo "The record ${record_name} is outside the approved DNS zones." >&2
    exit 1
  fi

  root_zone_id="$(hosted_zone_id_for_name "${root_fqdn}.")"
  if [[ -z "${root_zone_id}" ]]; then
    echo "Public Route 53 hosted zone ${root_fqdn}. was not found in the approved AWS account." >&2
    exit 1
  fi

  if [[ "${domain_fqdn}" != "${root_fqdn}" && ("${record_fqdn}" == "${domain_fqdn}" || "${record_fqdn}" == *".${domain_fqdn}") ]]; then
    domain_zone_id="$(hosted_zone_id_for_name "${domain_fqdn}.")"
    if [[ -n "${domain_zone_id}" ]] && is_child_zone_delegated "${root_zone_id##*/}" "${domain_fqdn}"; then
      printf '%s\n' "${domain_zone_id##*/}"
      return
    fi
  fi

  printf '%s\n' "${root_zone_id##*/}"
}

upsert_cname() {
  local record_name="$1"
  local record_value="$2"
  local hosted_zone_id
  local change_batch
  local change_id
  hosted_zone_id="$(hosted_zone_for_record "${record_name}")"
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

upsert_txt() {
  local record_name="$1"
  local record_value="$2"
  local hosted_zone_id
  local existing_record
  local record_values
  local ttl
  local change_batch
  local change_id

  hosted_zone_id="$(hosted_zone_for_record "${record_name}")"
  existing_record="$(aws route53 list-resource-record-sets \
    --hosted-zone-id "${hosted_zone_id}" \
    --output json | jq -c --arg name "${record_name}" \
      '[.ResourceRecordSets[] | select(.Name == $name and .Type == "TXT")][0] // empty')"
  if [[ -n "${existing_record}" ]]; then
    record_values="$(jq -c --arg value "${record_value}" \
      '((.ResourceRecords // []) | map(.Value) + [$value] | unique | map({Value:.}))' \
      <<<"${existing_record}")"
    ttl="$(jq -r '.TTL // 300' <<<"${existing_record}")"
  else
    record_values="$(jq -cn --arg value "${record_value}" '[{Value:$value}]')"
    ttl="300"
  fi
  change_batch="$(jq -cn \
    --arg name "${record_name}" \
    --argjson ttl "${ttl}" \
    --argjson records "${record_values}" \
    '{Changes:[{Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"TXT",TTL:$ttl,ResourceRecords:$records}}]}')"
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
    "PublishAlias=${publish_alias}" \
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

distribution_has_alias() {
  local target_distribution_id="$1"
  aws cloudfront get-distribution-config \
    --id "${target_distribution_id}" \
    --output json | jq -e --arg domain "${DOMAIN_NAME}" \
      '((.DistributionConfig.Aliases.Items // []) | index($domain)) != null' >/dev/null
}

transfer_domain_association() {
  local target_distribution_id="$1"
  local target_distribution_domain="$2"
  local conflicts
  local conflict_count
  local target_etag
  local transfer_output

  if distribution_has_alias "${target_distribution_id}"; then
    publish_alias="true"
    return
  fi

  conflicts="$(aws cloudfront list-domain-conflicts \
    --domain "${DOMAIN_NAME}" \
    --domain-control-validation-resource "DistributionId=${target_distribution_id}" \
    --output json)"
  conflict_count="$(jq '(.DomainConflicts // []) | length' <<<"${conflicts}")"
  if [[ "${conflict_count}" != "0" ]]; then
    echo "Existing CloudFront domain association detected; registering target ownership proof."
    upsert_txt "_${DOMAIN_NAME}." "\"${target_distribution_domain}\""
    target_etag="$(aws cloudfront get-distribution-config \
      --id "${target_distribution_id}" \
      --query ETag \
      --output text)"
    if ! transfer_output="$(aws cloudfront update-domain-association \
      --domain "${DOMAIN_NAME}" \
      --target-resource "DistributionId=${target_distribution_id}" \
      --if-match "${target_etag}" 2>&1)"; then
      echo "CloudFront could not transfer ${DOMAIN_NAME} to the target distribution." >&2
      echo "${transfer_output}" >&2
      echo "The source distribution must be disabled, or AWS Support must complete the transfer." >&2
      exit 1
    fi
  fi

  publish_alias="true"
}

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

transfer_domain_association "${distribution_id}" "${distribution_domain}"
if [[ "${publish_alias}" == "true" ]]; then
  aws cloudformation deploy \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --template-file infra/public-site.template.json \
    --no-fail-on-empty-changeset \
    --parameter-overrides \
      "PublicSiteBucketName=${PUBLIC_SITE_BUCKET_NAME}" \
      "DomainName=${DOMAIN_NAME}" \
      "CertificateArn=${CERTIFICATE_ARN}" \
      "PublishAlias=true" \
      "PriceClass=PriceClass_100"
  aws cloudfront wait distribution-deployed --id "${distribution_id}"
fi

upsert_cname "${DOMAIN_NAME}." "${distribution_domain}"

printf 'Published https://${DOMAIN_NAME}\n'
