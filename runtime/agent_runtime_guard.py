"""Pre-call guard for GraphKernel model actors.

GraphKernel is also used by local test and extension graphs. The mandatory NHI
check applies to production actors represented by this registry. CI separately
requires every registered platform graph agent to have an identity before merge.
"""
from __future__ import annotations

from runtime.agent_identity_registry import AGENT_IDENTITIES, effective_turn_limit, is_identity_enabled


def assert_graph_agent_runtime_allowed(actor_id: str, graph_id: str | None = None):
    identity = AGENT_IDENTITIES.get(actor_id)
    registered_graph_ids = {item.graph_id for item in AGENT_IDENTITIES.values() if item.graph_id is not None}
    if identity is None:
        if graph_id is not None and graph_id in registered_graph_ids:
            raise RuntimeError(f"registered graph agent has no non-human identity: {graph_id}:{actor_id}")
        return None
    if identity.graph_id is None:
        raise RuntimeError(f"graph agent cannot use a non-graph identity: {identity.identity_id}")
    if graph_id is not None and identity.graph_id != graph_id:
        raise RuntimeError(
            f"agent identity graph binding mismatch for {identity.identity_id}: "
            f"identity={identity.graph_id} execution={graph_id}"
        )
    if identity.authority != "A1":
        raise RuntimeError(f"graph model agent authority must remain A1: {identity.identity_id}")
    if identity.secret_access:
        raise RuntimeError(f"graph model agent cannot have secret access: {identity.identity_id}")
    if not is_identity_enabled(identity):
        raise RuntimeError(f"agent identity is disabled: {identity.identity_id}")
    effective = effective_turn_limit(identity)
    if effective < identity.max_turns:
        raise RuntimeError(
            f"runtime turn cap is below the provider contract for {identity.identity_id}: "
            f"effective={effective} provider={identity.max_turns}"
        )
    return identity
