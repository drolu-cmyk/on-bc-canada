from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from runtime.rds_data_api import DomainDataApiConfig, RdsDataApi, _parameters


class FakeDataClient:
    def __init__(self) -> None:
        self.execute_calls: list[dict] = []
        self.begin_calls: list[dict] = []
        self.commit_calls: list[dict] = []
        self.rollback_calls: list[dict] = []
        self.query_records: list[dict] = []

    def execute_statement(self, **kwargs):
        self.execute_calls.append(kwargs)
        if kwargs.get("formatRecordsAs") == "JSON":
            return {"formattedRecords": json.dumps(self.query_records)}
        return {"numberOfRecordsUpdated": 1}

    def begin_transaction(self, **kwargs):
        self.begin_calls.append(kwargs)
        return {"transactionId": "tx-001"}

    def commit_transaction(self, **kwargs):
        self.commit_calls.append(kwargs)
        return {}

    def rollback_transaction(self, **kwargs):
        self.rollback_calls.append(kwargs)
        return {}


class DomainDataApiTests(unittest.TestCase):
    def _config(self) -> DomainDataApiConfig:
        return DomainDataApiConfig(
            region="ca-central-1",
            cluster_arn="arn:aws:rds:ca-central-1:123456789012:cluster:domain",
            database="sozorockcanada",
            secret_arn="arn:aws:secretsmanager:ca-central-1:123456789012:secret:runtime",
        )

    def test_parameter_encoder_uses_typed_single_values_and_json_not_arrays(self):
        values = _parameters(
            {
                "flag": True,
                "count": 3,
                "score": 0.75,
                "metadata": {"source": "reviewed"},
                "missing": None,
                "name": "Agent evaluation",
            }
        )
        by_name = {item["name"]: item for item in values}
        self.assertEqual({"booleanValue": True}, by_name["flag"]["value"])
        self.assertEqual({"longValue": 3}, by_name["count"]["value"])
        self.assertEqual({"doubleValue": 0.75}, by_name["score"]["value"])
        self.assertEqual("JSON", by_name["metadata"]["typeHint"])
        self.assertNotIn("arrayValue", json.dumps(values))
        self.assertEqual({"isNull": True}, by_name["missing"]["value"])

    def test_execute_uses_secret_arn_and_never_database_password(self):
        client = FakeDataClient()
        api = RdsDataApi(self._config(), client=client)
        api.execute("UPDATE intelligence.work_entities SET canonical_name=:name WHERE entity_id=:id;", parameters={"name": "Name", "id": "x"})
        call = client.execute_calls[0]
        self.assertEqual(self._config().secret_arn, call["secretArn"])
        self.assertEqual(self._config().cluster_arn, call["resourceArn"])
        self.assertEqual("sozorockcanada", call["database"])
        self.assertNotIn("password", json.dumps(call).casefold())
        self.assertFalse(call["sql"].endswith(";"))

    def test_json_query_returns_object_rows(self):
        client = FakeDataClient()
        client.query_records = [{"entity_id": "capability:1", "metadata": {"pathway_id": "applied-ai-systems"}}]
        rows = RdsDataApi(self._config(), client=client).query("SELECT entity_id, metadata FROM intelligence.work_entities")
        self.assertEqual("capability:1", rows[0]["entity_id"])
        self.assertEqual("JSON", client.execute_calls[0]["formatRecordsAs"])

    def test_transaction_commits_and_rolls_back(self):
        client = FakeDataClient()
        api = RdsDataApi(self._config(), client=client)
        with api.transaction() as tx:
            api.execute("SELECT 1", transaction_id=tx)
        self.assertEqual(1, len(client.commit_calls))
        self.assertEqual(0, len(client.rollback_calls))

        with self.assertRaisesRegex(RuntimeError, "stop"):
            with api.transaction() as tx:
                api.execute("SELECT 2", transaction_id=tx)
                raise RuntimeError("stop")
        self.assertEqual(1, len(client.rollback_calls))

    def test_environment_profiles_are_explicit_and_canada_bound(self):
        common = {
            "SOZOROCK_DOMAIN_CLUSTER_ARN": "arn:aws:rds:ca-central-1:123:cluster:domain",
            "SOZOROCK_INTELLIGENCE_SECRET_ARN": "arn:intelligence",
            "SOZOROCK_LEARNING_SECRET_ARN": "arn:learning",
            "SOZOROCK_DOMAIN_MASTER_SECRET_ARN": "arn:master",
        }
        with patch.dict(os.environ, common, clear=True):
            self.assertEqual("arn:intelligence", DomainDataApiConfig.from_environment(access_profile="intelligence").secret_arn)
            self.assertEqual("arn:learning", DomainDataApiConfig.from_environment(access_profile="learning").secret_arn)
            self.assertEqual("arn:master", DomainDataApiConfig.from_environment(access_profile="migration").secret_arn)
        with patch.dict(os.environ, {**common, "SOZOROCK_DOMAIN_REGION": "us-east-1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ca-central-1"):
                DomainDataApiConfig.from_environment(access_profile="intelligence")

    def test_invalid_parameter_name_fails_before_api_call(self):
        client = FakeDataClient()
        api = RdsDataApi(self._config(), client=client)
        with self.assertRaises(ValueError):
            api.execute("SELECT :bad", parameters={"bad-name": 1})
        self.assertEqual([], client.execute_calls)


if __name__ == "__main__":
    unittest.main()
