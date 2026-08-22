from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import apply_domain_migrations as migrations


class FakeMigrationApi:
    def __init__(self) -> None:
        self.config = type("Config", (), {"database": "sozorockcanada"})()
        self.executed: list[dict] = []
        self.queries: list[dict] = []
        self.migration_table_exists = False
        self.applied: dict[str, str] = {}
        self.commits = 0
        self.rollbacks = 0

    def query(self, sql, *, parameters=None, transaction_id=None):
        self.queries.append({"sql": sql, "parameters": parameters, "transaction_id": transaction_id})
        if "to_regclass" in sql:
            return [{"table_name": "platform_meta.schema_migrations" if self.migration_table_exists else None}]
        if "schema_migrations" in sql and parameters:
            checksum = self.applied.get(parameters["migration_id"])
            return [{"checksum_sha256": checksum}] if checksum else []
        return []

    def execute(self, sql, *, parameters=None, transaction_id=None, continue_after_timeout=False):
        self.executed.append(
            {
                "sql": sql.strip(),
                "parameters": parameters or {},
                "transaction_id": transaction_id,
                "continue_after_timeout": continue_after_timeout,
            }
        )
        if "CREATE TABLE IF NOT EXISTS platform_meta.schema_migrations" in sql:
            self.migration_table_exists = True
        if "INSERT INTO platform_meta.schema_migrations" in sql and parameters:
            self.applied[parameters["migration_id"]] = parameters["checksum"]
        return {}

    @contextlib.contextmanager
    def transaction(self):
        try:
            yield "tx-001"
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


class FakeSecrets:
    def __init__(self) -> None:
        self.values = {
            "arn:intelligence": {"username": "sozorock_intelligence_rw", "password": "A-strong-generated-password-000001"},
            "arn:learning": {"username": "sozorock_learning_rw", "password": "A-strong-generated-password-000002"},
        }

    def get_secret_value(self, *, SecretId):
        return {"SecretString": json.dumps(self.values[SecretId])}


class DomainMigrationTests(unittest.TestCase):
    def test_repository_migration_is_marker_split_and_checksum_locked(self):
        path = Path("migrations/postgres/0001_domain_core.sql")
        migration_id, checksum, statements = migrations._migration(path)
        self.assertEqual("0001_domain_core", migration_id)
        self.assertEqual(64, len(checksum))
        self.assertGreater(len(statements), 20)
        self.assertTrue(any("intelligence.work_relations" in statement for statement in statements))
        self.assertTrue(any("learning.capability_provenance" in statement for statement in statements))
        self.assertFalse(any(migrations.MARKER in statement for statement in statements))

    def test_apply_migration_is_transactional_and_idempotent(self):
        api = FakeMigrationApi()
        applied = migrations.apply_migrations(api, applied_by="operator-001")
        self.assertEqual(["0001_domain_core"], applied)
        self.assertEqual(1, api.commits)
        self.assertEqual(0, api.rollbacks)
        self.assertTrue(api.migration_table_exists)
        first_execute_count = len(api.executed)
        self.assertEqual([], migrations.apply_migrations(api, applied_by="operator-001"))
        self.assertEqual(first_execute_count, len(api.executed))

    def test_changed_checksum_for_applied_migration_fails_closed(self):
        api = FakeMigrationApi()
        api.migration_table_exists = True
        api.applied["0001_domain_core"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum changed"):
            migrations.apply_migrations(api, applied_by="operator-001")

    def test_runtime_role_bootstrap_uses_secret_values_but_returns_names_only(self):
        api = FakeMigrationApi()
        roles = migrations.bootstrap_runtime_roles(
            api,
            secrets_client=FakeSecrets(),
            intelligence_secret_arn="arn:intelligence",
            learning_secret_arn="arn:learning",
        )
        self.assertEqual(["sozorock_intelligence_rw", "sozorock_learning_rw"], roles)
        combined_sql = "\n".join(item["sql"] for item in api.executed)
        self.assertIn("CREATE ROLE sozorock_intelligence_rw", combined_sql)
        self.assertIn("CREATE ROLE sozorock_learning_rw", combined_sql)
        self.assertIn("REVOKE UPDATE, DELETE ON learning.capability_decisions", combined_sql)
        self.assertIn("GRANT SELECT ON ALL TABLES IN SCHEMA intelligence TO sozorock_learning_rw", combined_sql)
        self.assertNotIn("A-strong-generated-password-000001", json.dumps(roles))
        self.assertNotIn("A-strong-generated-password-000002", json.dumps(roles))

    def test_secret_username_must_match_reviewed_role(self):
        secrets = FakeSecrets()
        secrets.values["arn:intelligence"]["username"] = "unexpected_admin"
        with self.assertRaisesRegex(RuntimeError, "reviewed role"):
            migrations.bootstrap_runtime_roles(
                FakeMigrationApi(),
                secrets_client=secrets,
                intelligence_secret_arn="arn:intelligence",
                learning_secret_arn="arn:learning",
            )

    def test_migration_parser_rejects_file_without_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.sql"
            path.write_text("-- migration_id: bad\nSELECT 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no statements"):
                migrations._migration(path)


if __name__ == "__main__":
    unittest.main()
