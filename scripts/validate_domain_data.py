#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "domain-data.template.json"
MIGRATIONS = ROOT / "migrations" / "postgres"
WORKFLOW = ROOT / ".github" / "workflows" / "domain-data-deploy.yml"
DEPLOY = ROOT / "scripts" / "deploy_domain_data.sh"
APPLY = ROOT / "scripts" / "apply_domain_migrations.py"
MARKER = "-- sozorock:statement"


def main() -> int:
    errors: list[str] = []
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    resources = template.get("Resources", {})
    parameters = template.get("Parameters", {})

    if parameters.get("EngineVersion", {}).get("Default") != "16.8":
        errors.append("domain data engine must default to Aurora PostgreSQL 16.8 LTS")
    if parameters.get("MaxCapacity", {}).get("Default") != 2:
        errors.append("pilot maximum capacity must default to 2 ACUs")
    if parameters.get("SecondsUntilAutoPause", {}).get("Default") != 900:
        errors.append("pilot auto-pause must default to 900 seconds")

    cluster = resources.get("DomainCluster", {})
    props = cluster.get("Properties", {})
    if cluster.get("Type") != "AWS::RDS::DBCluster":
        errors.append("DomainCluster must be AWS::RDS::DBCluster")
    required_cluster = {
        "Engine": "aurora-postgresql",
        "EngineMode": "provisioned",
        "EngineLifecycleSupport": "open-source-rds-extended-support-disabled",
        "ManageMasterUserPassword": True,
        "EnableHttpEndpoint": True,
        "EnableIAMDatabaseAuthentication": False,
        "StorageEncrypted": True,
        "DeletionProtection": True,
        "BackupRetentionPeriod": 7,
    }
    for key, expected in required_cluster.items():
        if props.get(key) != expected:
            errors.append(f"DomainCluster {key} must be {expected!r}")
    scaling = props.get("ServerlessV2ScalingConfiguration", {})
    if scaling.get("MinCapacity") != 0:
        errors.append("Aurora Serverless v2 minimum capacity must be zero for auto-pause")
    if scaling.get("SecondsUntilAutoPause") != {"Ref": "SecondsUntilAutoPause"}:
        errors.append("Aurora auto-pause interval must use the reviewed parameter")
    if not props.get("KmsKeyId") or not props.get("MasterUserSecret", {}).get("KmsKeyId"):
        errors.append("cluster storage and master secret must use the customer-managed KMS key")
    if cluster.get("DeletionPolicy") != "Retain" or cluster.get("UpdateReplacePolicy") != "Retain":
        errors.append("domain cluster must be retained on stack replacement/deletion")

    writer = resources.get("DomainWriter", {})
    writer_props = writer.get("Properties", {})
    if writer.get("Type") != "AWS::RDS::DBInstance":
        errors.append("DomainWriter must be AWS::RDS::DBInstance")
    if writer_props.get("DBInstanceClass") != "db.serverless":
        errors.append("DomainWriter must use db.serverless")
    if writer_props.get("PubliclyAccessible") is not False:
        errors.append("DomainWriter must not be publicly accessible")

    for subnet in ("DomainSubnetA", "DomainSubnetB"):
        if resources.get(subnet, {}).get("Properties", {}).get("MapPublicIpOnLaunch") is not False:
            errors.append(f"{subnet} must not map public IP addresses")
    sg = resources.get("DomainSecurityGroup", {}).get("Properties", {})
    if sg.get("SecurityGroupIngress") != []:
        errors.append("DomainSecurityGroup must have no network ingress")

    forbidden_resource_types = {
        "AWS::EC2::InternetGateway",
        "AWS::EC2::NatGateway",
        "AWS::Lambda::Function",
        "AWS::ECS::Service",
        "AWS::StepFunctions::StateMachine",
    }
    for name, resource in resources.items():
        if resource.get("Type") in forbidden_resource_types:
            errors.append(f"domain data foundation must not create {resource.get('Type')}: {name}")

    for secret_name, expected_user in (
        ("IntelligenceRuntimeSecret", "sozorock_intelligence_rw"),
        ("LearningRuntimeSecret", "sozorock_learning_rw"),
    ):
        secret = resources.get(secret_name, {})
        if secret.get("Type") != "AWS::SecretsManager::Secret":
            errors.append(f"missing runtime secret: {secret_name}")
            continue
        generated = secret.get("Properties", {}).get("GenerateSecretString", {})
        if expected_user not in generated.get("SecretStringTemplate", ""):
            errors.append(f"{secret_name} must bind the reviewed runtime role name")
        if generated.get("PasswordLength", 0) < 32:
            errors.append(f"{secret_name} password must be at least 32 characters")
        if not secret.get("Properties", {}).get("KmsKeyId"):
            errors.append(f"{secret_name} must use the domain KMS key")

    for policy_name in ("DomainMigrationPolicy", "IntelligenceDataApiPolicy", "LearningDataApiPolicy"):
        policy = resources.get(policy_name, {})
        if policy.get("Type") != "AWS::IAM::ManagedPolicy":
            errors.append(f"missing managed policy: {policy_name}")
            continue
        statements = policy.get("Properties", {}).get("PolicyDocument", {}).get("Statement", [])
        for statement in statements:
            actions = statement.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            forbidden = {"rds-data:*", "secretsmanager:*", "kms:*", "iam:PassRole"}
            if any(action in forbidden for action in actions):
                errors.append(f"{policy_name} grants a forbidden broad action")

    migration_files = sorted(MIGRATIONS.glob("*.sql"))
    if not migration_files:
        errors.append("at least one PostgreSQL migration is required")
    seen_ids: set[str] = set()
    for path in migration_files:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^-- migration_id:\s*([a-z0-9_]+)\s*$", text, re.MULTILINE)
        if match is None:
            errors.append(f"migration missing migration_id: {path.name}")
            continue
        migration_id = match.group(1)
        if migration_id in seen_ids:
            errors.append(f"duplicate migration_id: {migration_id}")
        seen_ids.add(migration_id)
        if text.count(MARKER) < 1:
            errors.append(f"migration has no Data API statement markers: {path.name}")
        if "CREATE SCHEMA IF NOT EXISTS learner_private" in text:
            errors.append("learner_private schema is outside domain data v0.1 scope")
        if re.search(r"CREATE\s+EXTENSION\s+.*vector", text, re.IGNORECASE):
            errors.append("pgvector must not be enabled without a concrete retrieval workload")
        for required in (
            "CREATE SCHEMA IF NOT EXISTS intelligence",
            "CREATE SCHEMA IF NOT EXISTS learning",
            "intelligence.work_relations",
            "learning.capability_provenance",
            "learning.learning_paths",
        ):
            if required not in text:
                errors.append(f"{path.name} missing required domain structure: {required}")

    apply_text = APPLY.read_text(encoding="utf-8") if APPLY.exists() else ""
    for requirement in (
        "schema_migrations",
        "checksum_sha256",
        "sozorock_intelligence_rw",
        "sozorock_learning_rw",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    ):
        if requirement not in apply_text:
            errors.append(f"migration runner missing boundary: {requirement}")
    if "print(password" in apply_text or "SecretString" in apply_text and "print(" in apply_text.split("SecretString", 1)[1][:200]:
        errors.append("migration runner must not print secret material")

    workflow_text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""
    if "workflow_dispatch:" not in workflow_text:
        errors.append("domain data deployment must be workflow_dispatch only")
    if "\n  push:" in workflow_text or "\n  pull_request:" in workflow_text:
        errors.append("domain data deployment must not run on push or pull request")
    for gate in ("DOMAIN_DATA_DEPLOYMENT_ENABLED", "DOMAIN_DATA_DEPLOY_ROLE_ARN"):
        if gate not in workflow_text:
            errors.append(f"domain data deployment workflow missing gate: {gate}")

    deploy_text = DEPLOY.read_text(encoding="utf-8") if DEPLOY.exists() else ""
    if "ca-central-1" not in deploy_text or "aws sts get-caller-identity" not in deploy_text:
        errors.append("domain data deploy script must verify account and Canada Central region")
    if "apply_domain_migrations.py" in deploy_text:
        errors.append("infrastructure deployment must not automatically apply database migrations")

    if errors:
        print("Domain data validation failed:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Domain data validation passed for private Aurora, Data API, reviewed migrations, and least-privilege runtime profiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
