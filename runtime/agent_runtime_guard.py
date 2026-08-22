"""Pre-call guard for GraphKernel model actors.

GraphKernel cannot inspect provider-specific SDK tools, so tool drift is checked by
the SDK construction audit. It can, however, enforce the stable non-human
identity, emergency disable state, authority, and effective turn-budget boundary
before any agent node handler is invoked.
"""
from __future__ import annotations

from runtime.agent_identity_registry import effective_turn_limit, identity_for_actor, is_identity_enabled


def assert_graph_agent_runtime_allowed(actor_id: str):
    identity = identity_for_actor(actor_id)
    if identity.graph_id is None:
        raise RuntimeError(f"graph agent cannot use a non-graph identity: {identity.identity_id}")
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
