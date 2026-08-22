"""Command-line operations for pseudonymous learner path progress."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from runtime.domain_store_factory import create_learning_store
from runtime.learner_progress_store import LearnerProgressStore


DEFAULT_LEARNER_DB = Path(os.getenv("SOZOROCK_LEARNER_DB", "local-data/learner-progress.sqlite3"))
DEFAULT_LEARNING_DB = Path(os.getenv("SOZOROCK_LEARNING_DB", "local-data/learning.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate pseudonymous learner path progress.")
    parser.add_argument("--db", default=str(DEFAULT_LEARNER_DB), help="Learner progress SQLite path.")
    parser.add_argument("--learning-db", default=str(DEFAULT_LEARNING_DB), help="Local Learning Graph SQLite path when SOZOROCK_DOMAIN_BACKEND=local.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    assign = subparsers.add_parser("assign", help="Assign the current active learning path to a pseudonymous learner reference.")
    assign.add_argument("--instance-id", required=True)
    assign.add_argument("--learner-ref", required=True)
    assign.add_argument("--cohort-id", required=True)
    assign.add_argument("--pathway-id", required=True)
    start = subparsers.add_parser("start-unit", help="Start one available learning unit.")
    start.add_argument("--instance-id", required=True)
    start.add_argument("--unit-id", required=True)
    complete = subparsers.add_parser("complete-practice", help="Complete one sprint or lab.")
    complete.add_argument("--instance-id", required=True)
    complete.add_argument("--unit-id", required=True)
    complete.add_argument("--evidence-ref", action="append", default=[])
    submit = subparsers.add_parser("submit-mission", help="Record one mission submission by secure artifact reference.")
    submit.add_argument("--submission-id", required=True)
    submit.add_argument("--instance-id", required=True)
    submit.add_argument("--unit-id", required=True)
    submit.add_argument("--artifact-ref", action="append", required=True)
    submit.add_argument("--artifact-type", action="append", required=True)
    submit.add_argument("--revision-ref", default=None)
    submit.add_argument("--defense-response-ref", default=None)
    submit.add_argument("--changed-scenario-response-ref", default=None)
    inspect = subparsers.add_parser("instance", help="Inspect one learner path instance.")
    inspect.add_argument("--instance-id", required=True)
    submission = subparsers.add_parser("submission", help="Inspect one learner mission submission.")
    submission.add_argument("--submission-id", required=True)
    evidence = subparsers.add_parser("accepted-evidence", help="Inspect accepted capability evidence for one learner path instance.")
    evidence.add_argument("--instance-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    progress = LearnerProgressStore(args.db)
    try:
        if args.command == "assign":
            result = progress.assign_active_path(
                learning_store=create_learning_store(args.learning_db),
                instance_id=args.instance_id,
                learner_ref=args.learner_ref,
                cohort_id=args.cohort_id,
                pathway_id=args.pathway_id,
            )
        elif args.command == "start-unit":
            result = progress.start_unit(args.instance_id, args.unit_id)
        elif args.command == "complete-practice":
            result = progress.complete_practice_unit(args.instance_id, args.unit_id, evidence_refs=tuple(args.evidence_ref))
        elif args.command == "submit-mission":
            result = progress.record_mission_submission(
                submission_id=args.submission_id,
                instance_id=args.instance_id,
                unit_id=args.unit_id,
                artifact_refs=tuple(args.artifact_ref),
                artifact_types=tuple(args.artifact_type),
                revision_ref=args.revision_ref,
                defense_response_ref=args.defense_response_ref,
                changed_scenario_response_ref=args.changed_scenario_response_ref,
            )
        elif args.command == "instance":
            result = progress.get_instance(args.instance_id)
        elif args.command == "submission":
            result = progress.get_submission(args.submission_id)
        else:
            result = {
                "instance_id": args.instance_id,
                "accepted_capability_evidence": progress.accepted_capability_evidence(args.instance_id),
            }
    except (KeyError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
