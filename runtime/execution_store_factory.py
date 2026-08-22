"""Select the generic graph execution store without changing graph logic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from runtime.aws_durable_execution import AwsDurableExecutionConfig, aws_execution_enabled
from runtime.durable_execution_store import DurableGraphExecutionStore
from runtime.graph_execution_store import GraphExecutionStore


EXECUTION_BACKEND_ENV = "SOZOROCK_EXECUTION_BACKEND"


def execution_backend() -> str:
    explicit = os.getenv(EXECUTION_BACKEND_ENV, "").strip().casefold()
    if explicit:
        if explicit not in {"local", "aws"}:
            raise RuntimeError("SOZOROCK_EXECUTION_BACKEND must be local or aws")
        return explicit
    return "aws" if aws_execution_enabled() else "local"


def create_execution_store(
    *,
    local_path: str | Path,
    aws_config: AwsDurableExecutionConfig | None = None,
    dynamodb_client: Any | None = None,
):
    backend = execution_backend()
    if backend == "local":
        return GraphExecutionStore(local_path)
    return DurableGraphExecutionStore(config=aws_config, client=dynamodb_client)
