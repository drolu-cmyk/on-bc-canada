#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${CERTIFICATE_REGION:=us-east-1}"
: "${ROOT_DOMAIN_NAME:=sozorock.ca}"
: "${DOMAIN_NAME:=www.sozorock.ca}"
: "${STACK_NAME:=sozorock-ca-public-site}"
: "${PUBLIC_SITE_BUCKET_NAME:?PUBLIC_SITE_BUCKET_NAME is required}"

CLOUDFRONT_ALIAS_ZONE_ID="Z2FDTNDATAQYW2"

command -v aws >/dev/null
command -v jq >/dev/null

if [[ "${ROOT_DOMAIN_NAME}" != "sozorock.ca" || "${DOMAIN_NAME}" != "www.sozorock.ca" ]]; then
  echo "This deployment is restricted to sozorock.ca and www.sozorock.ca." >&2
  exit 1
fi

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
  local existing_record
  local change_batch
  local change_id

  hosted_zone_id="$(hosted_zone_for_record "${record_name}")"
  existing_record="$(aws route53 list-resource-record-sets \
    --hosted-zone-id "${hosted_zone_id}" \
    --output json | jq -c --arg name "${record_name}" \
      '[.ResourceRecordSets[] | select(.Name == $name and .Type == "CNAME")][0] // empty')"
  if [[ -n "${existing_record}" ]]; then
    if jq -e --arg value "${record_value}" \
      '(.ResourceRecords // []) | length == 1 and .[0].Value == $value' \
      <<<"${existing_record}" >/dev/null; then
      return
    fi
    echo "Refusing to replace an unrelated CNAME at ${record_name}." >&2
    exit 1
  fi

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
  if [[ -n "${existing_record}" ]] && jq -e 'has("SetIdentifier") or has("HealthCheckId")' <<<"${existing_record}" >/dev/null; then
    echo "Refusing to replace a routed TXT record at ${record_name}." >&2
    exit 1
  fi
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

certificate_covers_domains() {
  local certificate_arn="$1"
  aws acm describe-certificate \
    --region "${CERTIFICATE_REGION}" \
    --certificate-arn "${certificate_arn}" \
    --output json | jq -e --arg root "${ROOT_DOMAIN_NAME}" --arg www "${DOMAIN_NAME}" '
      (.Certificate.Status == "ISSUED" or .Certificate.Status == "PENDING_VALIDATION")
      and ([.Certificate.SubjectAlternativeNames[]? | ascii_downcase | rtrimstr(".")] as $names
        | ($names | index($root)) != null and ($names | index($www)) != null)
    ' >/dev/null
}

ensure_certificate() {
  local certificate_arn=""
  local candidate
  local certificate_json
  local status
  local validation
  local record_name
  local record_value

  while IFS= read -r candidate; do
    if certificate_covers_domains "${candidate}"; then
      certificate_arn="${candidate}"
      break
    fi
  done < <(aws acm list-certificates \
    --region "${CERTIFICATE_REGION}" \
    --certificate-statuses ISSUED PENDING_VALIDATION \
    --output json | jq -r '.CertificateSummaryList[]?.CertificateArn')

  if [[ -z "${certificate_arn}" ]]; then
    certificate_arn="$(aws acm request-certificate \
      --region "${CERTIFICATE_REGION}" \
      --domain-name "${ROOT_DOMAIN_NAME}" \
      --subject-alternative-names "${DOMAIN_NAME}" \
      --validation-method DNS \
      --query CertificateArn \
      --output text)"
  fi

  for _ in $(seq 1 60); do
    certificate_json="$(aws acm describe-certificate \
      --region "${CERTIFICATE_REGION}" \
      --certificate-arn "${certificate_arn}" \
      --output json)"
    status="$(jq -r '.Certificate.Status' <<<"${certificate_json}")"
    if [[ "${status}" == "ISSUED" ]]; then
      printf '%s\n' "${certificate_arn}"
      return
    fi
    if [[ "${status}" == "FAILED" || "${status}" == "VALIDATION_TIMED_OUT" || "${status}" == "REVOKED" ]]; then
      echo "ACM certificate request failed: ${certificate_arn} (${status})" >&2
      exit 1
    fi

    while IFS= read -r validation; do
      [[ -z "${validation}" ]] && continue
      record_name="$(jq -r '.Name // empty' <<<"${validation}")"
      record_value="$(jq -r '.Value // empty' <<<"${validation}")"
      if [[ -n "${record_name}" && -n "${record_value}" ]]; then
        upsert_cname "${record_name}" "${record_value}"
      fi
    done < <(jq -c '.Certificate.DomainValidationOptions[]? | .ResourceRecord // empty' <<<"${certificate_json}")
    sleep 10
  done

  echo "Timed out waiting for ACM certificate issuance: ${certificate_arn}" >&2
  exit 1
}

deploy_stack() {
  local publish_alias="$1"
  aws cloudformation deploy \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --template-file infra/public-site.template.json \
    --no-fail-on-empty-changeset \
    --parameter-overrides \
      "PublicSiteBucketName=${PUBLIC_SITE_BUCKET_NAME}" \
      "RootDomainName=${ROOT_DOMAIN_NAME}" \
      "DomainName=${DOMAIN_NAME}" \
      "CertificateArn=${CERTIFICATE_ARN}" \
      "PublishAlias=${publish_alias}" \
      "PriceClass=PriceClass_100"
}

distribution_aliases() {
  local target_distribution_id="$1"
  aws cloudfront get-distribution-config \
    --id "${target_distribution_id}" \
    --output json | jq -r '(.DistributionConfig.Aliases.Items // [])[]?'
}

distribution_alias_count() {
  local target_distribution_id="$1"
  distribution_aliases "${target_distribution_id}" | awk 'NF {count += 1} END {print count + 0}'
}

distribution_has_alias() {
  local target_distribution_id="$1"
  local domain_name="$2"
  local normalized_domain="${domain_name%.}"
  distribution_aliases "${target_distribution_id}" | awk -v domain="${normalized_domain}" \
    'tolower($0) == tolower(domain) {found = 1} END {exit(found ? 0 : 1)}'
}

transfer_domain_associations() {
  local target_distribution_id="$1"
  local target_distribution_domain="$2"
  local domain_name
  local conflicts
  local conflict_count
  local target_etag
  local transfer_output

  for domain_name in "${ROOT_DOMAIN_NAME}" "${DOMAIN_NAME}"; do
    upsert_txt "_${domain_name}." "\"${target_distribution_domain%.}\""
  done

  for domain_name in "${ROOT_DOMAIN_NAME}" "${DOMAIN_NAME}"; do
    if distribution_has_alias "${target_distribution_id}" "${domain_name}"; then
      echo "CloudFront already serves ${domain_name}."
      continue
    fi

    conflicts="$(aws cloudfront list-domain-conflicts \
      --domain "${domain_name}" \
      --domain-control-validation-resource "DistributionId=${target_distribution_id}" \
      --output json)"
    conflict_count="$(jq '(.DomainConflicts // []) | length' <<<"${conflicts}")"
    if [[ "${conflict_count}" == "0" ]]; then
      echo "No existing CloudFront association was reported for ${domain_name}; the target distribution will attach it."
      continue
    fi

    target_etag="$(aws cloudfront get-distribution-config \
      --id "${target_distribution_id}" \
      --query ETag \
      --output text)"
    if ! transfer_output="$(aws cloudfront update-domain-association \
      --domain "${domain_name}" \
      --target-resource "DistributionId=${target_distribution_id}" \
      --if-match "${target_etag}" 2>&1)"; then
      echo "CloudFront could not transfer ${domain_name} to the target distribution." >&2
      echo "${transfer_output}" >&2
      echo "The source distribution must be disabled, or AWS Support must complete the transfer." >&2
      exit 1
    fi
    echo "CloudFront transfer accepted for ${domain_name}."
  done
}

replace_with_cloudfront_alias() {
  local record_name="$1"
  local target_distribution_domain="$2"
  local hosted_zone_id
  local existing_records
  local unsafe_values
  local delete_changes
  local target_dns_name="${target_distribution_domain%.}."
  local change_batch
  local change_id

  hosted_zone_id="$(hosted_zone_for_record "${record_name}")"
  existing_records="$(aws route53 list-resource-record-sets \
    --hosted-zone-id "${hosted_zone_id}" \
    --output json | jq -c --arg name "${record_name}" \
      '[.ResourceRecordSets[] | select(.Name == $name and (.Type == "A" or .Type == "AAAA" or .Type == "CNAME"))]')"

  if jq -e 'any(.[]; has("SetIdentifier") or has("HealthCheckId") or has("GeoLocation") or has("Failover") or has("Region"))' \
    <<<"${existing_records}" >/dev/null; then
    echo "Refusing to replace a routed or health-checked record at ${record_name}." >&2
    exit 1
  fi

  unsafe_values="$(jq -r '
    .[] |
    if .Type == "CNAME" then
      .ResourceRecords[]?.Value
    elif (.Type == "A" or .Type == "AAAA") then
      if has("AliasTarget") then .AliasTarget.DNSName else "literal-address-record" end
    else empty end
    | select(((ascii_downcase | rtrimstr(".")) | endswith(".cloudfront.net")) | not)
  ' <<<"${existing_records}")"
  if [[ -n "${unsafe_values}" ]]; then
    echo "Refusing to replace unrelated DNS values at ${record_name}: ${unsafe_values//$'\n'/, }" >&2
    exit 1
  fi

  delete_changes="$(jq -c '[.[] | select(.Type == "CNAME") | {Action:"DELETE",ResourceRecordSet:.}]' <<<"${existing_records}")"
  change_batch="$(jq -cn \
    --arg name "${record_name}" \
    --arg dns_name "${target_dns_name}" \
    --arg hosted_zone_id "${CLOUDFRONT_ALIAS_ZONE_ID}" \
    --argjson delete_changes "${delete_changes}" \
    '{Changes: ($delete_changes + [
      {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"A",AliasTarget:{HostedZoneId:$hosted_zone_id,DNSName:$dns_name,EvaluateTargetHealth:false}}},
      {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"AAAA",AliasTarget:{HostedZoneId:$hosted_zone_id,DNSName:$dns_name,EvaluateTargetHealth:false}}}
    ])}')"
  change_id="$(aws route53 change-resource-record-sets \
    --hosted-zone-id "${hosted_zone_id}" \
    --change-batch "${change_batch}" \
    --query "ChangeInfo.Id" \
    --output text)"
  aws route53 wait resource-record-sets-changed --id "${change_id}"
}

cleanup_failed_stack
CERTIFICATE_ARN="$(ensure_certificate)"

stack_status="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || true)"
distribution_id=""
distribution_domain=""
target_alias_count="0"
if [[ -n "${stack_status}" && "${stack_status}" != "None" ]]; then
  distribution_id="$(aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='PublicSiteDistributionId'].OutputValue" \
    --output text 2>/dev/null || true)"
  if [[ -n "${distribution_id}" && "${distribution_id}" != "None" ]]; then
    target_alias_count="$(distribution_alias_count "${distribution_id}")"
  fi
fi

if [[ -z "${distribution_id}" || "${distribution_id}" == "None" || "${target_alias_count}" == "0" ]]; then
  deploy_stack false
else
  echo "Preserving ${target_alias_count} hostname association(s) already attached to the target distribution."
fi

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
aws cloudfront wait invalidation-completed \
  --distribution-id "${distribution_id}" \
  --id "${invalidation_id}"

transfer_domain_associations "${distribution_id}" "${distribution_domain}"
aws cloudfront wait distribution-deployed --id "${distribution_id}"
deploy_stack true
aws cloudfront wait distribution-deployed --id "${distribution_id}"

for domain_name in "${ROOT_DOMAIN_NAME}" "${DOMAIN_NAME}"; do
  if ! distribution_has_alias "${distribution_id}" "${domain_name}"; then
    echo "CloudFront did not attach ${domain_name} to ${distribution_id}." >&2
    exit 1
  fi
done

replace_with_cloudfront_alias "${ROOT_DOMAIN_NAME}." "${distribution_domain}"
replace_with_cloudfront_alias "${DOMAIN_NAME}." "${distribution_domain}"

printf 'Published https://%s and https://%s\n' "${ROOT_DOMAIN_NAME}" "${DOMAIN_NAME}"
