"""Read-only operator commands for agent identities, tools, and runtime budgets."""
from __future__ import annotations

import argparse
import json
import sys

from runtime.agent_identity_audit import audit_agent_identity_policy
from runtime.agent_identity_registry import budget_manifest, identity_manifest, runtime_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate non-human agent identity policy.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate graph identity coverage and actual SDK agent/tool contracts.")
    subparsers.add_parser("manifest", help="Print registered non-human identities and workflow runtime budgets.")
    status = subparsers.add_parser("status", help="Read one agent's effective enabled and turn-budget state.")
    status.add_argument("--agent-id", required=True, help="Stable NHI ID or graph actor ID.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            report = audit_agent_identity_policy(construct_sdk_agents=True)
            payload = report.as_dict()
            code = 0 if report.passed else 2
        elif args.command == "manifest":
            payload = {
                "identities": identity_manifest(),
                "workflow_budgets": budget_manifest(),
                "write_controls": "Runtime disable state is supplied by deployment environment; this command is read-only.",
            }
            code = 0
        else:
            payload = runtime_status(args.agent_id)
            code = 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
