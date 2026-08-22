"""Command interface for graph registry and authority-harness checks."""
from __future__ import annotations

import argparse
import json
import sys

from runtime.platform_graph_harness import PlatformGraphHarness, harness_manifest
from runtime.platform_graph_registry import graph_registry_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate registered platform graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate all registered graph contracts and authority paths.")
    subparsers.add_parser("manifest", help="Print the graph registry contract manifest.")
    route = subparsers.add_parser("route", help="Resolve one explicit work type to its graph contract.")
    route.add_argument("--work-type", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            payload = harness_manifest()
            code = 0 if payload["passed"] else 2
        elif args.command == "manifest":
            payload = {"graphs": graph_registry_manifest()}
            code = 0
        else:
            payload = PlatformGraphHarness.route(args.work_type)
            code = 0
    except ValueError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
