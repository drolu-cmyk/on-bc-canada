#!/usr/bin/env bash
set -euo pipefail

if ! aws cloudfront list-functions --max-items 1 >/dev/null 2>&1; then
  echo "The AWS deployment role does not yet have CloudFront Function access." >&2
  echo "Update the sozorock-ca-github-oidc bootstrap stack before enabling the Canada domain migration." >&2
  exit 1
fi

printf 'CloudFront Function deployment preflight passed.\n'
