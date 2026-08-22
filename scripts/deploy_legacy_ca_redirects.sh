#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${STACK_NAME:=sozorock-ca-legacy-redirects}"
: "${LEGACY_HOSTED_ZONE_ID:=Z081121934QL55XA4WUZ}"
: "${LEGACY_ROOT_DOMAIN:=sozorock.ca}"
: "${LEGACY_WWW_DOMAIN:=www.sozorock.ca}"
: "${CANONICAL_ORIGIN:=https://canada.sozorock.com}"

actual_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${actual_account}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "AWS account mismatch: expected ${AWS_ACCOUNT_ID}, received ${actual_account}" >&2
  exit 1
fi
if [[ "${AWS_REGION}" != "ca-central-1" ]]; then
  echo "Legacy redirect service must run in ca-central-1." >&2
  exit 1
fi
if [[ "${LEGACY_ROOT_DOMAIN}" != "sozorock.ca" || "${LEGACY_WWW_DOMAIN}" != "www.sozorock.ca" ]]; then
  echo "Unexpected legacy hostname." >&2
  exit 1
fi
if [[ "${CANONICAL_ORIGIN}" != "https://canada.sozorock.com" ]]; then
  echo "Unexpected canonical redirect target." >&2
  exit 1
fi

zone_name="$(aws route53 get-hosted-zone --id "${LEGACY_HOSTED_ZONE_ID}" --query 'HostedZone.Name' --output text)"
if [[ "${zone_name}" != "sozorock.ca." ]]; then
  echo "Hosted zone ${LEGACY_HOSTED_ZONE_ID} is not sozorock.ca." >&2
  exit 1
fi

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file infra/legacy-ca-redirect.template.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "LegacyHostedZoneId=${LEGACY_HOSTED_ZONE_ID}" \
    "LegacyRootDomainName=${LEGACY_ROOT_DOMAIN}" \
    "LegacyWwwDomainName=${LEGACY_WWW_DOMAIN}" \
    "CanonicalOrigin=${CANONICAL_ORIGIN}"

stack_output() {
  aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

replace_dns_with_api_gateway() {
  local record_name="$1"
  local target_domain="$2"
  local target_zone="$3"
  local records
  local unsafe
  local deletes
  local change_batch
  local change_id

  records="$(aws route53 list-resource-record-sets \
    --hosted-zone-id "${LEGACY_HOSTED_ZONE_ID}" \
    --output json | jq -c --arg name "${record_name}." \
      '[.ResourceRecordSets[] | select(.Name == $name and (.Type == "A" or .Type == "AAAA" or .Type == "CNAME"))]')"

  unsafe="$(jq -r '
    .[] |
    if .Type == "CNAME" then .ResourceRecords[]?.Value
    elif has("AliasTarget") then .AliasTarget.DNSName
    else "literal-address-record" end
    | select(((ascii_downcase | rtrimstr(".")) | endswith(".cloudfront.net")) | not)
  ' <<<"${records}")"
  if [[ -n "${unsafe}" ]]; then
    echo "Refusing to replace unrelated DNS at ${record_name}: ${unsafe//$'\n'/, }" >&2
    exit 1
  fi

  deletes="$(jq -c '[.[] | select(.Type == "CNAME") | {Action:"DELETE",ResourceRecordSet:.}]' <<<"${records}")"
  change_batch="$(jq -cn \
    --arg name "${record_name}." \
    --arg dns "${target_domain%.}." \
    --arg zone "${target_zone}" \
    --argjson deletes "${deletes}" \
    '{Changes: ($deletes + [
      {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"A",AliasTarget:{HostedZoneId:$zone,DNSName:$dns,EvaluateTargetHealth:false}}},
      {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"AAAA",AliasTarget:{HostedZoneId:$zone,DNSName:$dns,EvaluateTargetHealth:false}}}
    ])}')"

  change_id="$(aws route53 change-resource-record-sets \
    --hosted-zone-id "${LEGACY_HOSTED_ZONE_ID}" \
    --change-batch "${change_batch}" \
    --query 'ChangeInfo.Id' \
    --output text)"
  aws route53 wait resource-record-sets-changed --id "${change_id}"
}

root_domain="$(stack_output RootRegionalDomainName)"
root_zone="$(stack_output RootRegionalHostedZoneId)"
www_domain="$(stack_output WwwRegionalDomainName)"
www_zone="$(stack_output WwwRegionalHostedZoneId)"

replace_dns_with_api_gateway "${LEGACY_ROOT_DOMAIN}" "${root_domain}" "${root_zone}"
replace_dns_with_api_gateway "${LEGACY_WWW_DOMAIN}" "${www_domain}" "${www_zone}"

verify_redirect() {
  local url="$1"
  local expected="$2"
  local response
  local status
  local location

  response="$(curl -sSI "${url}")"
  status="$(awk 'NR==1 {print $2}' <<<"${response}")"
  location="$(awk 'BEGIN{IGNORECASE=1} /^location:/ {$1=""; sub(/^ /,""); gsub(/\r/,""); print}' <<<"${response}")"
  if [[ "${status}" != "301" || "${location}" != "${expected}" ]]; then
    echo "Redirect verification failed for ${url}: status=${status}, location=${location}, expected=${expected}" >&2
    exit 1
  fi
}

verify_redirect "https://${LEGACY_ROOT_DOMAIN}/" "${CANONICAL_ORIGIN}/"
verify_redirect "https://${LEGACY_WWW_DOMAIN}/" "${CANONICAL_ORIGIN}/"
verify_redirect "https://${LEGACY_WWW_DOMAIN}/curriculum.html?source=legacy" "${CANONICAL_ORIGIN}/curriculum.html?source=legacy"

echo "Legacy .ca redirects are live and independent of CloudFront."
