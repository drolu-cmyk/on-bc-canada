#!/usr/bin/env python3
"""Validate the source-only public deployment contract and AWS template."""

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


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_contract() -> list[str]:
    instance_path = ROOT / "config/deployment.yaml"
    schema_path = ROOT / "schemas/deployment.schema.json"
    instance = load_yaml(instance_path)
    schema = load_json(schema_path)
    if Draft202012Validator is None:
        deployment = instance.get("deployment", {})
        return [
            "jsonschema is required for deployment semantic validation"
        ] if not deployment.get("deployment_id") else []
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda error: list(error.path))
    return [f"deployment contract {'.'.join(str(part) for part in error.path) or 'root'}: {error.message}" for error in errors]


def validate_template() -> list[str]:
    template = load_json(ROOT / "infra/public-site.template.json")
    resources = template.get("Resources", {})
    errors: list[str] = []
    required_types = {
        "PublicSiteBucket": "AWS::S3::Bucket",
        "PublicSiteOriginAccessControl": "AWS::CloudFront::OriginAccessControl",
        "PublicSiteDistribution": "AWS::CloudFront::Distribution",
        "PublicSiteBucketPolicy": "AWS::S3::BucketPolicy",
    }
    for name, resource_type in required_types.items():
        if resources.get(name, {}).get("Type") != resource_type:
            errors.append(f"missing resource type {name}={resource_type}")

    bucket = resources.get("PublicSiteBucket", {})
    bucket_properties = bucket.get("Properties", {})
    block = bucket_properties.get("PublicAccessBlockConfiguration", {})
    if any(block.get(key) is not True for key in ["BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"]):
        errors.append("public site bucket must block every public access mode")
    if bucket_properties.get("VersioningConfiguration", {}).get("Status") != "Enabled":
        errors.append("public site bucket versioning must be enabled")
    if not bucket_properties.get("BucketEncryption", {}).get("ServerSideEncryptionConfiguration"):
        errors.append("public site bucket encryption is required")
    if bucket.get("DeletionPolicy") != "Retain" or bucket.get("UpdateReplacePolicy") != "Retain":
        errors.append("public site bucket retention policies are required")

    distribution = resources.get("PublicSiteDistribution", {})
    distribution_config = distribution.get("Properties", {}).get("DistributionConfig", {})
    if distribution_config.get("DefaultRootObject") != "index.html":
        errors.append("CloudFront default root object must be index.html")
    behavior = distribution_config.get("DefaultCacheBehavior", {})
    if behavior.get("AllowedMethods") != ["GET", "HEAD"]:
        errors.append("public site cache behavior must allow GET and HEAD only")
    if behavior.get("ViewerProtocolPolicy") != "redirect-to-https":
        errors.append("public site cache behavior must redirect to HTTPS")
    if not distribution_config.get("Origins"):
        errors.append("CloudFront must define a private S3 origin")
    return errors


def validate_source_boundary() -> list[str]:
    deployment = load_yaml(ROOT / "config/deployment.yaml").get("deployment", {})
    errors: list[str] = []
    if deployment.get("status") != "source_only":
        errors.append("deployment status must remain source_only")
    public_site = deployment.get("public_site", {})
    learner_services = deployment.get("learner_services", {})
    for section, values in [("public_site", public_site), ("learner_services", learner_services)]:
        if values.get("external_side_effects") != "disabled":
            errors.append(f"{section}.external_side_effects must be disabled")
    if public_site.get("data_collection") != "disabled":
        errors.append("public_site.data_collection must be disabled")
    if learner_services.get("intake") != "disabled":
        errors.append("learner_services.intake must be disabled")
    if learner_services.get("production_data") != "disabled":
        errors.append("learner_services.production_data must be disabled")
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
    print("Deployment validation passed for the source-only public shell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
