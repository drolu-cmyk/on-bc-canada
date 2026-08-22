#!/usr/bin/env python3
"""Apply reviewed PostgreSQL domain migrations through RDS Data API.

The script uses the RDS-managed master secret only for migration/bootstrap work.
Generated runtime passwords are read from Secrets Manager and used to create or
rotate restricted PostgreSQL roles; secret values are never printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from runtime.rds_data_api import DomainDataApiConfig, RdsDataApi


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_DIR = ROOT / "migrations" / "postgres"
MARKER = "-- sozorock:statement"
MIGRATION_ID_RE = re.compile(r"^-- migration_id:\s*([a-z0-9_]+)\s*$", re.MULTILINE)
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
EXPECTED_RUNTIME_ROLES = {
    "intelligence": "sozorock_intelligence_rw",
    "learning": "sozorock_learning_rw",
}


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _migration(path: Path) -> tuple[str, str, list[str]]:
    text = path.read_text(encoding="utf-8")
    match = MIGRATION_ID_RE.search(text)
    if match is None:
        raise ValueError(f"migration has no migration_id: {path.name}")
    migration_id = match.group(1)
    statements = [part.strip() for part in text.split(MARKER)[1:] if part.strip()]
    if not statements:
        raise ValueError(f"migration has no statements: {path.name}")
    for statement in statements:
        if MARKER in statement:
            raise ValueError(f"nested statement marker in migration: {path.name}")
    return migration_id, _checksum(text), statements


def _quote_literal(value: str) -> str:
    if "\x00" in value:
        raise ValueError("database secret contains a null byte")
    return "'" + value.replace("'", "''") + "'"


def _secret(client: Any, arn: str, expected_username: str) -> dict[str, str]:
    response = client.get_secret_value(SecretId=arn)
    raw = response.get("SecretString")
    if not raw:
        raise RuntimeError(f"database runtime secret has no SecretString: {arn}")
    value = json.loads(raw)
    username = str(value.get("username") or "")
    password = str(value.get("password") or "")
    if username != expected_username or not ROLE_RE.fullmatch(username):
        raise RuntimeError(f"database secret username does not match reviewed role: {expected_username}")
    if len(password) < 24:
        raise RuntimeError(f"database password for {expected_username} is unexpectedly short")
    return {"username": username, "password": password}


def _table_exists(api: RdsDataApi) -> bool:
    rows = api.query("SELECT to_regclass('platform_meta.schema_migrations')::text AS table_name")
    return bool(rows and rows[0].get("table_name"))


def _applied_checksum(api: RdsDataApi, migration_id: str) -> str | None:
    if not _table_exists(api):
        return None
    rows = api.query(
        "SELECT checksum_sha256 FROM platform_meta.schema_migrations WHERE migration_id = :migration_id",
        parameters={"migration_id": migration_id},
    )
    return str(rows[0]["checksum_sha256"]) if rows else None


def apply_migrations(api: RdsDataApi, *, applied_by: str) -> list[str]:
    applied: list[str] = []
    for path in sorted(MIGRATION_DIR.glob("*.sql")):
        migration_id, checksum, statements = _migration(path)
        existing = _applied_checksum(api, migration_id)
        if existing:
            if existing != checksum:
                raise RuntimeError(f"applied migration checksum changed: {migration_id}")
            continue
        with api.transaction() as transaction_id:
            for statement in statements:
                api.execute(statement, transaction_id=transaction_id, continue_after_timeout=True)
            api.execute(
                """
                INSERT INTO platform_meta.schema_migrations (migration_id, checksum_sha256, applied_by)
                VALUES (:migration_id, :checksum, :applied_by)
                """,
                parameters={
                    "migration_id": migration_id,
                    "checksum": checksum,
                    "applied_by": applied_by,
                },
                transaction_id=transaction_id,
            )
        applied.append(migration_id)
    if not list(MIGRATION_DIR.glob("*.sql")):
        raise RuntimeError("no PostgreSQL migrations were found")
    return applied


def _role_sql(username: str, password: str) -> str:
    if not ROLE_RE.fullmatch(username):
        raise ValueError("invalid PostgreSQL role name")
    password_literal = _quote_literal(password)
    return f"""
    DO $sozorock$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{username}') THEN
        CREATE ROLE {username} LOGIN PASSWORD {password_literal};
      ELSE
        ALTER ROLE {username} WITH LOGIN PASSWORD {password_literal};
      END IF;
    END
    $sozorock$
    """


def bootstrap_runtime_roles(
    api: RdsDataApi,
    *,
    secrets_client: Any,
    intelligence_secret_arn: str,
    learning_secret_arn: str,
) -> list[str]:
    intelligence = _secret(secrets_client, intelligence_secret_arn, EXPECTED_RUNTIME_ROLES["intelligence"])
    learning = _secret(secrets_client, learning_secret_arn, EXPECTED_RUNTIME_ROLES["learning"])
    for value in (intelligence, learning):
        api.execute(_role_sql(value["username"], value["password"]), continue_after_timeout=True)

    statements = [
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        "REVOKE ALL ON SCHEMA intelligence FROM PUBLIC",
        "REVOKE ALL ON SCHEMA learning FROM PUBLIC",
        f"GRANT CONNECT ON DATABASE {api.config.database} TO {intelligence['username']}",
        f"GRANT CONNECT ON DATABASE {api.config.database} TO {learning['username']}",
        f"GRANT USAGE ON SCHEMA intelligence TO {intelligence['username']}",
        f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA intelligence TO {intelligence['username']}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA intelligence GRANT SELECT, INSERT, UPDATE ON TABLES TO {intelligence['username']}",
        f"GRANT USAGE ON SCHEMA intelligence TO {learning['username']}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA intelligence TO {learning['username']}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA intelligence GRANT SELECT ON TABLES TO {learning['username']}",
        f"GRANT USAGE ON SCHEMA learning TO {learning['username']}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA learning TO {learning['username']}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA learning TO {learning['username']}",
        f"REVOKE UPDATE, DELETE ON learning.capability_decisions FROM {learning['username']}",
        f"REVOKE UPDATE, DELETE ON learning.learning_path_decisions FROM {learning['username']}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA learning GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {learning['username']}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA learning GRANT USAGE, SELECT ON SEQUENCES TO {learning['username']}",
        f"ALTER ROLE {intelligence['username']} SET search_path = intelligence, public",
        f"ALTER ROLE {learning['username']} SET search_path = learning, intelligence, public",
    ]
    for statement in statements:
        api.execute(statement, continue_after_timeout=True)
    return [intelligence["username"], learning["username"]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply reviewed SozoRock Canada PostgreSQL domain migrations.")
    parser.add_argument("--applied-by", required=True, help="Accountable operator identifier recorded with the migration.")
    parser.add_argument("--intelligence-secret-arn", required=True)
    parser.add_argument("--learning-secret-arn", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = DomainDataApiConfig.from_environment(access_profile="migration")
        api = RdsDataApi(config)
        import boto3

        secrets = boto3.client("secretsmanager", region_name=config.region)
        applied = apply_migrations(api, applied_by=args.applied_by)
        roles = bootstrap_runtime_roles(
            api,
            secrets_client=secrets,
            intelligence_secret_arn=args.intelligence_secret_arn,
            learning_secret_arn=args.learning_secret_arn,
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "database": config.database,
                "region": config.region,
                "applied_migrations": applied,
                "runtime_roles": roles,
                "secret_values_exposed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
