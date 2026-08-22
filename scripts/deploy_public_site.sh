#!/usr/bin/env bash
set -euo pipefail

: "${AWS_ACCOUNT_ID:=891377012881}"
: "${AWS_REGION:=ca-central-1}"
: "${CERTIFICATE_REGION:=us-east-1}"
: "${CANONICAL_DOMAIN:=canada.sozorock.com}"
: "${CANONICAL_DNS_ZONE:=canada.sozorock.com}"
: "${STACK_NAME:=sozorock-ca-public-site}"
: "${PUBLIC_SITE_BUCKET_NAME:?PUBLIC_SITE_BUCKET_NAME is required}"

CLOUDFRONT_ALIAS_ZONE_ID="Z2FDTNDATAQYW2"

command -v aws >/dev/null
command -v jq >/dev/null

if [[ "${CANONICAL_DOMAIN}" != "canada.sozorock.com" || "${CANONICAL_DNS_ZONE}" != "canada.sozorock.com" ]]; then
  echo "This deployment is restricted to canada.sozorock.com." >&2
  exit 1
fi
if [[ "${AWS_REGION}" != "ca-central-1" || "${CERTIFICATE_REGION}" != "us-east-1" ]]; then
  echo "Canada workloads must use ca-central-1 and CloudFront certificates must use us-east-1." >&2
  exit 1
fi

actual_account="$(aws sts get-caller-identity --query Account --output text)"
if [[ "${actual_account}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "AWS account mismatch: expected ${AWS_ACCOUNT_ID}, received ${actual_account}" >&2
  exit 1
fi

hosted_zone_id="$(aws route53 list-hosted-zones-by-name \
  --dns-name "${CANONICAL_DNS_ZONE}." \
  --output json | jq -r --arg zone "${CANONICAL_DNS_ZONE}." \
  '[.HostedZones[] | select(.Name == $zone and .Config.PrivateZone == false) | .Id] | first // empty')"
if [[ -z "${hosted_zone_id}" ]]; then
  echo "Public Route 53 zone ${CANONICAL_DNS_ZONE}. was not found in account ${AWS_ACCOUNT_ID}." >&2
  exit 1
fi
hosted_zone_id="${hosted_zone_id##*/}"

certificate_arn=""
while IFS= read -r candidate; do
  if aws acm describe-certificate \
      --region "${CERTIFICATE_REGION}" \
      --certificate-arn "${candidate}" \
      --output json | jq -e --arg domain "${CANONICAL_DOMAIN}" '
        .Certificate.Status == "ISSUED"
        and ([.Certificate.SubjectAlternativeNames[]? | ascii_downcase | rtrimstr(".")] | index($domain) != null)
      ' >/dev/null; then
    certificate_arn="${candidate}"
    break
  fi
done < <(aws acm list-certificates \
  --region "${CERTIFICATE_REGION}" \
  --certificate-statuses ISSUED \
  --output json | jq -r '.CertificateSummaryList[]?.CertificateArn')

if [[ -z "${certificate_arn}" ]]; then
  echo "No issued us-east-1 certificate covers ${CANONICAL_DOMAIN}." >&2
  exit 1
fi

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file infra/public-site.template.json \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "PublicSiteBucketName=${PUBLIC_SITE_BUCKET_NAME}" \
    "CanonicalDomainName=${CANONICAL_DOMAIN}" \
    "CertificateArn=${certificate_arn}" \
    "PublishAlias=true" \
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

change_batch="$(jq -cn \
  --arg name "${CANONICAL_DOMAIN}." \
  --arg dns_name "${distribution_domain%.}." \
  --arg zone "${CLOUDFRONT_ALIAS_ZONE_ID}" '
  {Changes:[
    {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"A",AliasTarget:{HostedZoneId:$zone,DNSName:$dns_name,EvaluateTargetHealth:false}}},
    {Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"AAAA",AliasTarget:{HostedZoneId:$zone,DNSName:$dns_name,EvaluateTargetHealth:false}}}
  ]}')"
change_id="$(aws route53 change-resource-record-sets \
  --hosted-zone-id "${hosted_zone_id}" \
  --change-batch "${change_batch}" \
  --query 'ChangeInfo.Id' \
  --output text)"
aws route53 wait resource-record-sets-changed --id "${change_id}"

printf 'Published https://%s on CloudFront distribution %s. Legacy .ca redirects are managed separately.\n' "${CANONICAL_DOMAIN}" "${distribution_id}"
