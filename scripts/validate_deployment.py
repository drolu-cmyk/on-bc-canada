#!/usr/bin/env python3
"""Validate the Canada public-site deployment contract and canonical AWS template."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ORIGIN = "https://canada.sozorock.com"
CANONICAL_DOMAIN = "canada.sozorock.com"
LEGACY_DOMAINS = ["sozorock.ca", "www.sozorock.ca"]
AWS_ACCOUNT_ID = "891377012881"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_contract() -> list[str]:
    instance = load_yaml(ROOT / "config/deployment.yaml")
    schema = load_json(ROOT / "schemas/deployment.schema.json")
    if Draft202012Validator is None:
        return ["jsonschema is required for deployment semantic validation"]
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda error: list(error.path))
    return [f"deployment contract {'.'.join(str(part) for part in error.path) or 'root'}: {error.message}" for error in errors]


def validate_template() -> list[str]:
    template = load_json(ROOT / "infra/public-site.template.json")
    resources = template.get("Resources", {})
    parameters = template.get("Parameters", {})
    errors: list[str] = []

    if parameters.get("CanonicalDomainName", {}).get("Default") != CANONICAL_DOMAIN:
        errors.append("CanonicalDomainName must default to canada.sozorock.com")
    if "LegacyRootDomainName" in parameters or "LegacyWwwDomainName" in parameters:
        errors.append("canonical CloudFront template must not parameterize legacy .ca aliases")
    if parameters.get("PublishAlias", {}).get("Default") != "true":
        errors.append("canonical CloudFront alias must be enabled by default")

    required_types = {
        "PublicSiteBucket": "AWS::S3::Bucket",
        "PublicSiteOriginAccessControl": "AWS::CloudFront::OriginAccessControl",
        "CanonicalRouteFunction": "AWS::CloudFront::Function",
        "PublicSiteDistribution": "AWS::CloudFront::Distribution",
        "PublicSiteBucketPolicy": "AWS::S3::BucketPolicy",
    }
    for name, expected_type in required_types.items():
        if resources.get(name, {}).get("Type") != expected_type:
            errors.append(f"missing resource type {name}={expected_type}")
    if "LegacyDomainRedirectFunction" in resources:
        errors.append("legacy redirects must not share the canonical CloudFront distribution")

    route_function = resources.get("CanonicalRouteFunction", {}).get("Properties", {})
    if route_function.get("AutoPublish") is not True:
        errors.append("canonical route function must auto-publish")
    if route_function.get("FunctionConfig", {}).get("Runtime") != "cloudfront-js-2.0":
        errors.append("canonical route function must use cloudfront-js-2.0")
    function_code = route_function.get("FunctionCode", "")
    for required_fragment in ["/index.html", ".html", "request.uri = uri + '.html'"]:
        if required_fragment not in function_code:
            errors.append(f"canonical route function is missing {required_fragment}")

    bucket = resources.get("PublicSiteBucket", {})
    props = bucket.get("Properties", {})
    block = props.get("PublicAccessBlockConfiguration", {})
    if any(block.get(key) is not True for key in ["BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"]):
        errors.append("public site bucket must block every public access mode")
    if props.get("VersioningConfiguration", {}).get("Status") != "Enabled":
        errors.append("public site bucket versioning must be enabled")
    if not props.get("BucketEncryption", {}).get("ServerSideEncryptionConfiguration"):
        errors.append("public site bucket encryption is required")

    distribution = resources.get("PublicSiteDistribution", {})
    config = distribution.get("Properties", {}).get("DistributionConfig", {})
    aliases = config.get("Aliases", {})
    expected_aliases = ["PublishCustomDomain", [{"Ref": "CanonicalDomainName"}], {"Ref": "AWS::NoValue"}]
    if aliases.get("Fn::If") != expected_aliases:
        errors.append("CloudFront must conditionally attach only canada.sozorock.com")
    if config.get("IPV6Enabled") is not True or "IsIPV6Enabled" in config:
        errors.append("CloudFront IPv6 configuration is invalid")
    if config.get("DefaultRootObject") != "index.html":
        errors.append("CloudFront default root object must be index.html")
    if config.get("ViewerCertificate", {}).get("MinimumProtocolVersion") != "TLSv1.2_2021":
        errors.append("CloudFront TLS policy must be TLSv1.2_2021")

    origins = config.get("Origins", [])
    origin = next((item for item in origins if item.get("Id") == "PublicSiteOrigin"), None)
    if not origin:
        errors.append("CloudFront must define PublicSiteOrigin")
    else:
        if origin.get("OriginAccessControlId") != {"Ref": "PublicSiteOriginAccessControl"}:
            errors.append("CloudFront S3 origin must use the origin access control")
        if origin.get("S3OriginConfig") != {"OriginAccessIdentity": ""}:
            errors.append("CloudFront OAC S3 origin must use an empty OriginAccessIdentity")

    behavior = config.get("DefaultCacheBehavior", {})
    if behavior.get("AllowedMethods") != ["GET", "HEAD"]:
        errors.append("public site must allow GET and HEAD only")
    if behavior.get("ViewerProtocolPolicy") != "redirect-to-https":
        errors.append("public site must redirect HTTP to HTTPS")
    associations = behavior.get("FunctionAssociations", [])
    expected_association = {
        "EventType": "viewer-request",
        "FunctionARN": {"Fn::GetAtt": ["CanonicalRouteFunction", "FunctionARN"]},
    }
    if associations != [expected_association]:
        errors.append("canonical CloudFront distribution must use only CanonicalRouteFunction on viewer-request")
    return errors


def validate_source_boundary() -> list[str]:
    deployment = load_yaml(ROOT / "config/deployment.yaml").get("deployment", {})
    public_site = deployment.get("public_site", {})
    automation = deployment.get("automation", {})
    errors: list[str] = []

    if automation.get("account_id") != AWS_ACCOUNT_ID:
        errors.append("automation.account_id must be 891377012881")
    if automation.get("region") != "ca-central-1":
        errors.append("automation.region must be ca-central-1")
    if public_site.get("canonical_origin") != CANONICAL_ORIGIN:
        errors.append("canonical_origin must be https://canada.sozorock.com")
    if public_site.get("canonical_domain_name") != CANONICAL_DOMAIN:
        errors.append("canonical_domain_name must be canada.sozorock.com")
    if public_site.get("canonical_dns_zone_name") != CANONICAL_DOMAIN:
        errors.append("canonical_dns_zone_name must be canada.sozorock.com")
    if public_site.get("legacy_domain_names") != LEGACY_DOMAINS:
        errors.append("legacy domains must remain sozorock.ca and www.sozorock.ca")
    if public_site.get("legacy_redirect_status") != 301:
        errors.append("legacy redirect status must remain 301")
    if public_site.get("certificate_region") != "us-east-1":
        errors.append("CloudFront certificate region must be us-east-1")
    for required in ["index.html", "privacy.html", "terms.html", "404.html"]:
        if not (ROOT / "site" / required).is_file():
            errors.append(f"site/{required} is required")
    return errors


def main() -> int:
    errors = validate_contract() + validate_template() + validate_source_boundary()
    if errors:
        print("Deployment validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Deployment validation passed for canonical canada.sozorock.com with clean routes and legacy .ca redirects separated from CloudFront.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
