"""Command-line entrypoint for constrained implementation and delivery review."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.implementation_delivery_runner import (
    implementation_delivery_summary,
    resume_implementation_delivery,
    start_implementation_delivery,
)
from runtime.implementation_workspace import RegisteredVerificationRunner, StagingWorkspace
from runtime.openai_implementation_provider import OpenAIImplementationProvider
from runtime.product_development_store import ProductDevelopmentStore


DEFAULT_DB = Path(os.getenv("SOZOROCK_IMPLEMENTATION_DB", "local-data/implementation-delivery.sqlite3"))
VERIFICATION_REGISTRY = {
    "spec-validation": ("python", "scripts/validate_specs.py"),
    "public-copy": ("python", "scripts/validate_public_copy.py"),
    "site-validation": ("python", "scripts/validate_site.py"),
    "deployment-validation": ("python", "scripts/validate_deployment.py"),
    "runtime-tests": ("python", "-m", "unittest", "discover", "-s", "runtime", "-p", "test_*.py", "-v"),
    "compiler-tests": (
        "python",
        "-c",
        "import sys,unittest;sys.path.insert(0,'compiler/src');s=unittest.defaultTestLoader.discover('compiler/tests');r=unittest.TextTestRunner(verbosity=2).run(s);raise SystemExit(0 if r.wasSuccessful() else 1)",
    ),
}


def _workspace_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", required=True, help="Existing isolated staging workspace root.")
    parser.add_argument("--allow-root", action="append", required=True, help="Relative repository root the staging executor may modify.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run constrained staging implementation from an authorized product packet.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Implementation graph SQLite path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Generate, apply, and verify a staging implementation.")
    _workspace_args(start)
    start.add_argument("--product-db", required=True)
    start.add_argument("--product-execution-id", required=True)
    start.add_argument("--context-path", action="append", required=True)
    start.add_argument("--required-verification", action="append", required=True, choices=tuple(VERIFICATION_REGISTRY))
    start.add_argument("--execution-id", default=None)

    resume = subparsers.add_parser("resume", help="Resolve the A3 merge/deploy review after checking staging integrity.")
    _workspace_args(resume)
    resume.add_argument("--execution-id", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--deny", action="store_true")
    resume.add_argument("--approver-id", required=True)
    resume.add_argument("--note", required=True)

    status = subparsers.add_parser("status", help="Read stored delivery state without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIImplementationProvider:
    return OpenAIImplementationProvider()


def _workspace(args) -> StagingWorkspace:
    return StagingWorkspace(args.workspace_root, allowed_roots=tuple(args.allow_root))


def _verifier(args) -> RegisteredVerificationRunner:
    return RegisteredVerificationRunner(args.workspace_root, VERIFICATION_REGISTRY)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = GraphExecutionStore(args.db)
    try:
        if args.command == "start":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for a live staging implementation")
            release_record = ProductDevelopmentStore(args.product_db).get_release_record(args.product_execution_id)
            if release_record is None:
                raise KeyError(f"product release record not found: {args.product_execution_id}")
            request = {
                "source_execution_id": args.product_execution_id,
                "release_record": release_record,
                "context_paths": args.context_path,
                "allowed_verification_ids": list(VERIFICATION_REGISTRY),
                "required_verification_ids": args.required_verification,
            }
            execution = start_implementation_delivery(
                provider=_provider(),
                execution_store=store,
                workspace=_workspace(args),
                verifier=_verifier(args),
                execution_id=args.execution_id or f"implementation-{uuid.uuid4().hex[:10]}",
                request=request,
            )
        elif args.command == "resume":
            execution = resume_implementation_delivery(
                provider=_provider(),
                execution_store=store,
                workspace=_workspace(args),
                verifier=_verifier(args),
                execution_id=args.execution_id,
                approved=bool(args.approve),
                approver_id=args.approver_id,
                note=args.note,
            )
        else:
            execution, _ = store.load_execution(args.execution_id)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(implementation_delivery_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
