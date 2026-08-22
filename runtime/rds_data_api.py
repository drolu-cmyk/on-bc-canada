"""Small RDS Data API adapter for the PostgreSQL domain data plane.

The adapter never reads or transports database passwords. RDS Data API resolves
credentials from the configured Secrets Manager secret after IAM authorization.
"""
from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from typing import Any, Iterator


DOMAIN_REGION_ENV = "SOZOROCK_DOMAIN_REGION"
DOMAIN_CLUSTER_ARN_ENV = "SOZOROCK_DOMAIN_CLUSTER_ARN"
DOMAIN_DATABASE_ENV = "SOZOROCK_DOMAIN_DATABASE"
INTELLIGENCE_SECRET_ARN_ENV = "SOZOROCK_INTELLIGENCE_SECRET_ARN"
LEARNING_SECRET_ARN_ENV = "SOZOROCK_LEARNING_SECRET_ARN"
MASTER_SECRET_ARN_ENV = "SOZOROCK_DOMAIN_MASTER_SECRET_ARN"
DEFAULT_REGION = "ca-central-1"
DEFAULT_DATABASE = "sozorockcanada"


@dataclass(frozen=True)
class DomainDataApiConfig:
    region: str
    cluster_arn: str
    database: str
    secret_arn: str

    @classmethod
    def from_environment(cls, *, access_profile: str) -> "DomainDataApiConfig":
        region = os.getenv(DOMAIN_REGION_ENV, DEFAULT_REGION).strip() or DEFAULT_REGION
        if region != DEFAULT_REGION:
            raise RuntimeError("domain data must remain in ca-central-1")
        cluster_arn = os.getenv(DOMAIN_CLUSTER_ARN_ENV, "").strip()
        if not cluster_arn:
            raise RuntimeError("SOZOROCK_DOMAIN_CLUSTER_ARN is required")
        database = os.getenv(DOMAIN_DATABASE_ENV, DEFAULT_DATABASE).strip() or DEFAULT_DATABASE
        secret_env = {
            "intelligence": INTELLIGENCE_SECRET_ARN_ENV,
            "learning": LEARNING_SECRET_ARN_ENV,
            "migration": MASTER_SECRET_ARN_ENV,
        }.get(access_profile)
        if secret_env is None:
            raise ValueError("access_profile must be intelligence, learning, or migration")
        secret_arn = os.getenv(secret_env, "").strip()
        if not secret_arn:
            raise RuntimeError(f"{secret_env} is required")
        return cls(region=region, cluster_arn=cluster_arn, database=database, secret_arn=secret_arn)


def _field(value: Any) -> tuple[dict[str, Any], str | None]:
    if value is None:
        return {"isNull": True}, None
    if isinstance(value, bool):
        return {"booleanValue": value}, None
    if isinstance(value, int) and not isinstance(value, bool):
        return {"longValue": value}, None
    if isinstance(value, float):
        return {"doubleValue": value}, None
    if isinstance(value, (dict, list, tuple)):
        return {"stringValue": json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}, "JSON"
    return {"stringValue": str(value)}, None


def _parameters(values: dict[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, value in sorted((values or {}).items()):
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"invalid Data API parameter name: {name!r}")
        field, type_hint = _field(value)
        parameter: dict[str, Any] = {"name": name, "value": field}
        if type_hint:
            parameter["typeHint"] = type_hint
        result.append(parameter)
    return result


class RdsDataApi:
    """Execute single PostgreSQL statements with explicit transaction support."""

    def __init__(self, config: DomainDataApiConfig, *, client: Any | None = None) -> None:
        self.config = config
        if client is None:
            import boto3

            client = boto3.client("rds-data", region_name=config.region)
        self.client = client

    def _base(self) -> dict[str, Any]:
        return {
            "resourceArn": self.config.cluster_arn,
            "secretArn": self.config.secret_arn,
            "database": self.config.database,
        }

    def execute(
        self,
        sql: str,
        *,
        parameters: dict[str, Any] | None = None,
        transaction_id: str | None = None,
        continue_after_timeout: bool = False,
    ) -> dict[str, Any]:
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise ValueError("SQL statement is required")
        request = self._base()
        request.update(
            {
                "sql": statement,
                "parameters": _parameters(parameters),
                "continueAfterTimeout": bool(continue_after_timeout),
            }
        )
        if transaction_id:
            request["transactionId"] = transaction_id
        return self.client.execute_statement(**request)

    def query(
        self,
        sql: str,
        *,
        parameters: dict[str, Any] | None = None,
        transaction_id: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise ValueError("SQL statement is required")
        request = self._base()
        request.update(
            {
                "sql": statement,
                "parameters": _parameters(parameters),
                "formatRecordsAs": "JSON",
            }
        )
        if transaction_id:
            request["transactionId"] = transaction_id
        response = self.client.execute_statement(**request)
        raw = response.get("formattedRecords")
        if not raw:
            return []
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
            raise RuntimeError("RDS Data API returned an unexpected JSON record shape")
        return parsed

    def begin(self) -> str:
        response = self.client.begin_transaction(**self._base())
        transaction_id = str(response.get("transactionId") or "")
        if not transaction_id:
            raise RuntimeError("RDS Data API did not return a transaction ID")
        return transaction_id

    def commit(self, transaction_id: str) -> None:
        self.client.commit_transaction(transactionId=transaction_id, **self._base())

    def rollback(self, transaction_id: str) -> None:
        self.client.rollback_transaction(transactionId=transaction_id, **self._base())

    @contextlib.contextmanager
    def transaction(self) -> Iterator[str]:
        transaction_id = self.begin()
        try:
            yield transaction_id
        except Exception:
            self.rollback(transaction_id)
            raise
        else:
            self.commit(transaction_id)
