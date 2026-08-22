#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "legacy-ca-redirect.template.json"
SCRIPT = ROOT / "scripts" / "deploy_legacy_ca_redirects.sh"


def main() -> int:
    errors: list[str] = []
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    resources = template.get("Resources", {})

    expected_types = {
        "RedirectCertificate": "AWS::CertificateManager::Certificate",
        "RedirectFunctionRole": "AWS::IAM::Role",
        "RedirectFunction": "AWS::Lambda::Function",
        "RedirectApi": "AWS::ApiGatewayV2::Api",
        "RedirectIntegration": "AWS::ApiGatewayV2::Integration",
        "RedirectRoute": "AWS::ApiGatewayV2::Route",
        "RedirectStage": "AWS::ApiGatewayV2::Stage",
        "RootDomain": "AWS::ApiGatewayV2::DomainName",
        "WwwDomain": "AWS::ApiGatewayV2::DomainName",
        "RootMapping": "AWS::ApiGatewayV2::ApiMapping",
        "WwwMapping": "AWS::ApiGatewayV2::ApiMapping",
    }
    for name, resource_type in expected_types.items():
        if resources.get(name, {}).get("Type") != resource_type:
            errors.append(f"missing {name}={resource_type}")

    certificate = resources.get("RedirectCertificate", {}).get("Properties", {})
    if certificate.get("ValidationMethod") != "DNS":
        errors.append("legacy certificate must use DNS validation")
    if certificate.get("DomainName") != {"Ref": "LegacyRootDomainName"}:
        errors.append("legacy certificate must cover sozorock.ca")
    if {"Ref": "LegacyWwwDomainName"} not in certificate.get("SubjectAlternativeNames", []):
        errors.append("legacy certificate must cover www.sozorock.ca")

    api = resources.get("RedirectApi", {}).get("Properties", {})
    if api.get("ProtocolType") != "HTTP" or api.get("IpAddressType") != "dualstack":
        errors.append("legacy redirect API must be a dual-stack HTTP API")

    function = resources.get("RedirectFunction", {}).get("Properties", {})
    code = function.get("Code", {}).get("ZipFile", "")
    if function.get("Runtime") != "nodejs22.x":
        errors.append("legacy redirect Lambda must use nodejs22.x")
    if "statusCode: 301" not in code:
        errors.append("legacy redirect Lambda must return HTTP 301")
    if "rawPath" not in code or "rawQueryString" not in code:
        errors.append("legacy redirect Lambda must preserve path and query string")
    if "CANONICAL_ORIGIN" not in code:
        errors.append("legacy redirect Lambda must use the fixed canonical origin")

    for domain_name in ["RootDomain", "WwwDomain"]:
        configs = resources.get(domain_name, {}).get("Properties", {}).get("DomainNameConfigurations", [])
        if len(configs) != 1:
            errors.append(f"{domain_name} must define exactly one domain configuration")
            continue
        config = configs[0]
        if config.get("EndpointType") != "REGIONAL":
            errors.append(f"{domain_name} must be REGIONAL")
        if config.get("SecurityPolicy") != "TLS_1_2":
            errors.append(f"{domain_name} must require TLS 1.2")
        if config.get("IpAddressType") != "dualstack":
            errors.append(f"{domain_name} must support dualstack")

    script = SCRIPT.read_text(encoding="utf-8")
    required_script_tokens = [
        "Z081121934QL55XA4WUZ",
        "https://canada.sozorock.com",
        "endswith(\".cloudfront.net\")",
        "Refusing to replace unrelated DNS",
        "RootRegionalDomainName",
        "RootRegionalHostedZoneId",
        "WwwRegionalDomainName",
        "WwwRegionalHostedZoneId",
        "status=${status}",
    ]
    for token in required_script_tokens:
        if token not in script:
            errors.append(f"legacy redirect deploy script missing safety token: {token}")

    if errors:
        print("Legacy redirect validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Legacy .ca regional redirect validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
