"""Select reviewed domain stores without changing graph business rules."""
from __future__ import annotations

import os
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.learning_graph import LearningGraphStore
from runtime.postgres_capability_graph import PostgresCapabilityGraphStore
from runtime.postgres_learning_graph import PostgresLearningGraphStore
from runtime.postgres_work_intelligence import PostgresWorkIntelligenceStore
from runtime.work_intelligence import WorkIntelligenceStore


DOMAIN_BACKEND_ENV = "SOZOROCK_DOMAIN_BACKEND"


def domain_backend() -> str:
    value = os.getenv(DOMAIN_BACKEND_ENV, "local").strip().casefold() or "local"
    if value not in {"local", "postgres"}:
        raise RuntimeError("SOZOROCK_DOMAIN_BACKEND must be local or postgres")
    return value


def create_work_intelligence_store(local_path: str | Path):
    if domain_backend() == "postgres":
        return PostgresWorkIntelligenceStore()
    return WorkIntelligenceStore(local_path)


def create_capability_store(local_path: str | Path):
    if domain_backend() == "postgres":
        return PostgresCapabilityGraphStore()
    return CapabilityGraphStore(local_path)


def create_learning_store(local_path: str | Path):
    if domain_backend() == "postgres":
        return PostgresLearningGraphStore()
    return LearningGraphStore(local_path)
