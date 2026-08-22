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

for url in \
  "https://${LEGACY_ROOT_DOMAIN}/" \
  "https://${LEGACY_WWW_DOMAIN}/" \
  "https://${LEGACY_WWW_DOMAIN}/curriculum.html?source=legacy"; do
  response="$(curl -sSI "${url}")"
  status="$(awk 'NR==1 {print $2}' <<<"${response}")"
  location="$(awk 'BEGIN{IGNORECASE=1} /^location:/ {$1=""; sub(/^ /,""); gsub(/\r/,""); print}' <<<"${response}")"
  if [[ "${status}" != "301" || "${location}" != "${CANONICAL_ORIGIN}${url#https://${LEGACY_ROOT_DOMAIN}}" && "${location}" != "${CANONICAL_ORIGIN}${url#https://${LEGACY_WWW_DOMAIN}}" ]]; then
    echo "Redirect verification failed for ${url}: status=${status}, location=${location}" >&2
    exit 1
  fi
done

echo "Legacy .ca redirects are live and independent of CloudFront."
