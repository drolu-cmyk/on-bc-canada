"""Command interface for platform graph registry, routing, and authority checks."""
from __future__ import annotations

import argparse
import json
import os
import sys

from runtime.openai_platform_orchestrator import OpenAIPlatformOrchestrator, OrchestrationEnvelope
from runtime.platform_graph_harness import DispatchRequest, PlatformGraphHarness, harness_manifest
from runtime.platform_graph_registry import GRAPH_CONTRACTS, graph_registry_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate registered platform graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate graph contracts, authority paths, data boundaries, handoffs, and dispatch cases.")
    subparsers.add_parser("manifest", help="Print the graph registry contract manifest.")

    route = subparsers.add_parser("route", help="Resolve one explicit work type to its graph contract.")
    route.add_argument("--work-type", required=True)

    dispatch = subparsers.add_parser("dispatch", help="Validate graph, data, and requested effect without a model call.")
    dispatch.add_argument("--work-type", required=True, choices=sorted(GRAPH_CONTRACTS))
    dispatch.add_argument("--mode", required=True, choices=("analyze", "authorize", "execute"))
    dispatch.add_argument("--effect", required=True)
    dispatch.add_argument("--data-class", action="append", default=[])

    model = subparsers.add_parser("model-context", help="Validate declared model data classes without a model call.")
    model.add_argument("--work-type", required=True, choices=sorted(GRAPH_CONTRACTS))
    model.add_argument("--data-class", action="append", default=[])

    handoff = subparsers.add_parser("handoff", help="Validate one registered cross-graph or graph-to-store handoff.")
    handoff.add_argument("--source-work-type", required=True, choices=sorted(GRAPH_CONTRACTS))
    handoff.add_argument("--target-kind", required=True, choices=("graph", "store"))
    handoff.add_argument("--target-id", required=True)
    handoff.add_argument("--data-class", action="append", default=[])

    propose = subparsers.add_parser("propose", help="Let the typed manager propose a first work type, then validate it deterministically.")
    propose.add_argument("--objective", required=True)
    propose.add_argument("--mode", required=True, choices=("analyze", "authorize", "execute"))
    propose.add_argument("--effect", required=True)
    propose.add_argument("--data-class", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    harness = PlatformGraphHarness()
    try:
        if args.command == "validate":
            payload = harness_manifest()
            code = 0 if payload["passed"] else 2
        elif args.command == "manifest":
            payload = {"graphs": graph_registry_manifest()}
            code = 0
        elif args.command == "route":
            payload = harness.route(args.work_type)
            code = 0
        elif args.command == "dispatch":
            decision = harness.validate_dispatch(
                DispatchRequest(
                    work_type=args.work_type,
                    mode=args.mode,
                    requested_effect=args.effect,
                    data_classes=tuple(args.data_class),
                )
            )
            payload = decision.as_dict()
            code = 0 if decision.allowed else 2
        elif args.command == "model-context":
            decision = harness.validate_model_context(args.work_type, tuple(args.data_class))
            payload = decision.as_dict()
            code = 0 if decision.allowed else 2
        elif args.command == "handoff":
            payload = harness.validate_handoff(
                source_work_type=args.source_work_type,
                target_kind=args.target_kind,
                target_id=args.target_id,
                payload_data_classes=tuple(args.data_class),
            )
            code = 0 if payload["allowed"] else 2
        else:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for a live platform route proposal")
            envelope = OrchestrationEnvelope(
                objective=args.objective,
                mode=args.mode,
                requested_effect=args.effect,
                declared_data_classes=tuple(args.data_class),
            )
            proposal = OpenAIPlatformOrchestrator().propose(envelope)
            decision = harness.validate_dispatch(
                DispatchRequest(
                    work_type=proposal["work_type"],
                    mode=args.mode,
                    requested_effect=args.effect,
                    data_classes=tuple(args.data_class),
                )
            )
            payload = {"proposal": proposal, "decision": decision.as_dict()}
            code = 0 if decision.allowed else 2
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
