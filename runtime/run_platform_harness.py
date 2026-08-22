"""Command interface for platform registry audit and bounded routing."""
from __future__ import annotations

import argparse
import json
import os
import sys

from runtime.openai_platform_orchestrator import OpenAIPlatformOrchestrator, OrchestrationEnvelope
from runtime.platform_harness import (
    DispatchRequest,
    PlatformHarness,
    WORKFLOW_CONTRACTS,
    evaluate_harness_cases,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the platform graph harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List registered workflow contracts.")
    subparsers.add_parser("audit", help="Audit registry drift and run deterministic harness cases.")

    route = subparsers.add_parser("route", help="Validate an explicit workflow dispatch without a model call.")
    route.add_argument("--workflow-key", required=True, choices=sorted(WORKFLOW_CONTRACTS))
    route.add_argument("--mode", required=True, choices=("analyze", "authorize", "execute"))
    route.add_argument("--effect", required=True)
    route.add_argument("--data-class", action="append", default=[])

    model = subparsers.add_parser("model-context", help="Validate declared model data classes without a model call.")
    model.add_argument("--workflow-key", required=True, choices=sorted(WORKFLOW_CONTRACTS))
    model.add_argument("--data-class", action="append", default=[])

    handoff = subparsers.add_parser("handoff", help="Validate a registered cross-graph or graph-to-store handoff.")
    handoff.add_argument("--source-workflow-key", required=True, choices=sorted(WORKFLOW_CONTRACTS))
    handoff.add_argument("--target-kind", required=True, choices=("graph", "store"))
    handoff.add_argument("--target-id", required=True)
    handoff.add_argument("--data-class", action="append", default=[])

    propose = subparsers.add_parser("propose", help="Let the typed manager propose a workflow, then validate it deterministically.")
    propose.add_argument("--objective", required=True)
    propose.add_argument("--mode", required=True, choices=("analyze", "authorize", "execute"))
    propose.add_argument("--effect", required=True)
    propose.add_argument("--data-class", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    harness = PlatformHarness()
    try:
        if args.command == "list":
            payload = {"workflows": harness.list_contracts()}
            code = 0
        elif args.command == "audit":
            registry = harness.audit_registry()
            cases = evaluate_harness_cases(harness)
            payload = {"registry": registry, "cases": cases, "passed": registry["passed"] and cases["passed"]}
            code = 0 if payload["passed"] else 2
        elif args.command == "route":
            decision = harness.validate_dispatch(
                DispatchRequest(
                    workflow_key=args.workflow_key,
                    mode=args.mode,
                    requested_effect=args.effect,
                    data_classes=tuple(args.data_class),
                )
            )
            payload = decision.as_dict()
            code = 0 if decision.allowed else 2
        elif args.command == "model-context":
            decision = harness.validate_model_context(args.workflow_key, tuple(args.data_class))
            payload = decision.as_dict()
            code = 0 if decision.allowed else 2
        elif args.command == "handoff":
            payload = harness.validate_handoff(
                source_workflow_key=args.source_workflow_key,
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
                    workflow_key=proposal["workflow_key"],
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
