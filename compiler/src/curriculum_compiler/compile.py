#!/usr/bin/env python3
"""Compile versioned module specifications into a portable release package.

The compiler is intentionally offline and deterministic. Model providers are
optional authoring aids; they are not part of the release path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from . import COMPILER_VERSION


class CompileError(ValueError):
    """Raised when a release cannot satisfy the curriculum contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompileError(f"{path}: expected a YAML object")
    return value


def load_modules(source_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    modules: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(source_dir.glob("*.yaml")):
        modules.append((path, _load_yaml(path)))
    if not modules:
        raise CompileError(f"{source_dir}: no module specifications found")
    return modules


def validate_modules(modules: list[tuple[Path, dict[str, Any]]]) -> None:
    required = {"module_id", "title", "version", "domain", "outcomes", "evidence", "delivery", "change_resilience"}
    public_claim_terms = re.compile(
        r"\b(accredited|degree|diploma|employment guarantee|immigration pathway|study permit|licensed professional)\b",
        re.IGNORECASE,
    )
    provider_terms = re.compile(r"\b(AWS|Amazon|Azure|GCP|Google|OpenAI|ChatGPT|Grok)\b")
    module_ids: set[str] = set()

    for path, module in modules:
        label = path.as_posix()
        missing = sorted(required - set(module))
        if missing:
            raise CompileError(f"{label}: missing required fields: {', '.join(missing)}")

        module_id = module["module_id"]
        if not isinstance(module_id, str) or not re.fullmatch(r"[A-Z]{2,4}-[0-9]{3}", module_id):
            raise CompileError(f"{label}: module_id must use the stable PREFIX-000 form")
        if module_id in module_ids:
            raise CompileError(f"{label}: duplicate module_id {module_id}")
        module_ids.add(module_id)

        outcomes = module["outcomes"]
        evidence = module["evidence"]
        if not isinstance(outcomes, list) or len(outcomes) < 3:
            raise CompileError(f"{label}: at least three outcomes are required")
        if not isinstance(evidence, list) or not evidence:
            raise CompileError(f"{label}: at least one evidence item is required")

        outcome_ids = {item.get("id") for item in outcomes if isinstance(item, dict)}
        if None in outcome_ids or len(outcome_ids) != len(outcomes):
            raise CompileError(f"{label}: outcome ids must be present and unique")
        evidence_ids = {item.get("artifact_id") for item in evidence if isinstance(item, dict)}
        if None in evidence_ids or len(evidence_ids) != len(evidence):
            raise CompileError(f"{label}: evidence artifact ids must be present and unique")

        mapped_outcomes: set[str] = set()
        for item in outcomes:
            statement = str(item.get("statement", ""))
            if len(statement) < 20:
                raise CompileError(f"{label}: outcome {item.get('id')} is too short")
            if provider_terms.search(statement):
                raise CompileError(f"{label}: outcome {item.get('id')} names a replaceable provider")
            if public_claim_terms.search(statement):
                raise CompileError(f"{label}: outcome {item.get('id')} contains a restricted public claim")

        for item in evidence:
            if not isinstance(item, dict):
                raise CompileError(f"{label}: evidence entries must be objects")
            refs = item.get("maps_to_outcomes")
            if not isinstance(refs, list) or not refs:
                raise CompileError(f"{label}: evidence {item.get('artifact_id')} has no outcome mapping")
            unknown = sorted(set(refs) - outcome_ids)
            if unknown:
                raise CompileError(f"{label}: evidence {item.get('artifact_id')} references unknown outcomes {unknown}")
            mapped_outcomes.update(refs)
            if not item.get("rubric_id"):
                raise CompileError(f"{label}: evidence {item.get('artifact_id')} has no rubric_id")

        missing_mappings = sorted(outcome_ids - mapped_outcomes)
        if missing_mappings:
            raise CompileError(f"{label}: outcomes without evidence: {', '.join(missing_mappings)}")

        delivery = module["delivery"]
        if not isinstance(delivery, dict) or not delivery.get("accessibility_path"):
            raise CompileError(f"{label}: an accessibility path is required")

        resilience = module["change_resilience"]
        for key in ("invariant_concepts", "replaceable_tools", "substitution_test", "refresh_triggers"):
            if not resilience.get(key):
                raise CompileError(f"{label}: change_resilience.{key} is required")

        lab = module.get("safe_lab")
        if not isinstance(lab, dict):
            raise CompileError(f"{label}: safe_lab is required for generated lab guidance")
        for key in ("allowed_data", "prohibited_data", "stop_conditions"):
            if not lab.get(key):
                raise CompileError(f"{label}: safe_lab.{key} is required")


def _module_page(module: dict[str, Any], release_id: str) -> str:
    outcomes = "\n".join(f"- **{item['id']}** — {item['statement']}" for item in module["outcomes"])
    evidence = "\n".join(
        f"- `{item['artifact_id']}` ({item['type']}) — {', '.join(item['maps_to_outcomes'])}"
        for item in module["evidence"]
    )
    delivery = module["delivery"]
    resilience = module["change_resilience"]
    return f"""# {module['module_id']}: {module['title']}

Release: `{release_id}`  
Module version: `{module['version']}`  
Domain: `{module['domain']}`

{module.get('description', '')}

## Learning outcomes

{outcomes}

## Evidence to prepare

{evidence}

## Delivery pattern

- Weeks: {delivery['weeks']}
- Live sessions: {', '.join(delivery['live_sessions'])}
- Independent work: {', '.join(delivery['independent_work'])}
- Equivalent access path: {delivery['accessibility_path']}

## Durable concepts

{', '.join(resilience['invariant_concepts'])}

The implementation instrument can change. The reasoning, evidence, and review standard remain the same.
"""


def _run_of_show(module: dict[str, Any], release_id: str) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "module_id": module["module_id"],
        "module_version": module["version"],
        "title": module["title"],
        "session_sequence": [
            {"order": index, "session": session, "purpose": "facilitate, check understanding, and record exceptions"}
            for index, session in enumerate(module["delivery"]["live_sessions"], start=1)
        ],
        "independent_work": module["delivery"]["independent_work"],
        "human_review_points": [
            "accessibility or accommodation exception",
            "safety or privacy concern",
            "assessment dispute or appeal",
        ],
        "completion_boundary": "Attendance and submission records do not by themselves establish competency or accreditation.",
    }


def _lab_page(module: dict[str, Any], release_id: str) -> str:
    lab = module["safe_lab"]
    allowed = "\n".join(f"- {item}" for item in lab["allowed_data"])
    prohibited = "\n".join(f"- {item}" for item in lab["prohibited_data"])
    stops = "\n".join(f"- {item}" for item in lab["stop_conditions"])
    return f"""# Safe lab brief: {module['module_id']}

Release: `{release_id}`

Use only the following allowed inputs:

{allowed}

Never use:

{prohibited}

Stop immediately and route for review when:

{stops}

The lab must be disposable, least-privilege, time-limited, cost-bounded, and reset before reuse. Capture only the evidence required by the module specification.
"""


def _rubric(module: dict[str, Any], release_id: str) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "module_id": module["module_id"],
        "rubric_id": f"{module['module_id']}-RUBRIC",
        "scale": [
            {"score": 0, "label": "not demonstrated"},
            {"score": 1, "label": "emerging"},
            {"score": 2, "label": "developing"},
            {"score": 3, "label": "proficient"},
            {"score": 4, "label": "defensible and transferable"},
        ],
        "criteria": [
            {
                "criterion_id": f"{outcome['id']}-CRITERION",
                "outcome_id": outcome["id"],
                "description": outcome["statement"],
                "evidence_required": [item["artifact_id"] for item in module["evidence"] if outcome["id"] in item["maps_to_outcomes"]],
                "human_review_required": True,
            }
            for outcome in module["outcomes"]
        ],
        "attendance_certificate_note": "This rubric is quality evidence and is separate from a certificate of attendance.",
    }


def compile_release(source_dir: Path, output_dir: Path, program_id: str, release_version: str) -> Path:
    modules = load_modules(source_dir)
    validate_modules(modules)
    normalized = [
        {"source_path": path.relative_to(source_dir).as_posix(), "module": module}
        for path, module in modules
    ]
    source_digest = _sha256_bytes(_canonical(normalized))
    release_id = f"{program_id}@{release_version}@{source_digest[:12]}"
    release_dir = output_dir / "releases" / program_id / release_version
    if release_dir.exists():
        shutil.rmtree(release_dir)
    for folder in ("learner/pages", "instructor/run-of-show", "labs", "rubrics", "feedback"):
        (release_dir / folder).mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, str]] = []
    evidence_index: list[dict[str, Any]] = []
    for path, module in modules:
        module_id = module["module_id"]
        learner_path = release_dir / "learner/pages" / f"{module_id}.md"
        learner_path.write_text(_module_page(module, release_id), encoding="utf-8")
        run_path = release_dir / "instructor/run-of-show" / f"{module_id}.json"
        run_path.write_bytes(_canonical(_run_of_show(module, release_id)))
        lab_path = release_dir / "labs" / f"{module_id}.md"
        lab_path.write_text(_lab_page(module, release_id), encoding="utf-8")
        rubric_path = release_dir / "rubrics" / f"{module_id}.json"
        rubric_path.write_bytes(_canonical(_rubric(module, release_id)))
        feedback_path = release_dir / "feedback" / f"{module_id}.json"
        feedback_path.write_bytes(
            _canonical(
                {
                    "release_id": release_id,
                    "module_id": module_id,
                    "feedback_fields": ["evidence_reference", "strength", "next_revision", "reviewer_note"],
                    "model_feedback": {"status": "provisional", "human_confirmation_required": True},
                }
            )
        )
        for artifact in (learner_path, run_path, lab_path, rubric_path, feedback_path):
            artifacts.append(
                {
                    "path": artifact.relative_to(release_dir).as_posix(),
                    "sha256": _sha256_file(artifact),
                    "module_id": module_id,
                }
            )
        for item in module["evidence"]:
            evidence_index.append(
                {
                    "module_id": module_id,
                    "outcome_ids": sorted(item["maps_to_outcomes"]),
                    "artifact_id": item["artifact_id"],
                    "artifact_type": item["type"],
                    "rubric_id": item["rubric_id"],
                    "required_for_attendance_certificate": bool(item.get("required_for_certificate", False)),
                }
            )

    evidence_path = release_dir / "evidence-index.json"
    evidence_path.write_bytes(_canonical({"release_id": release_id, "items": evidence_index}))
    artifacts.append({"path": "evidence-index.json", "sha256": _sha256_file(evidence_path), "module_id": "program"})

    checks = {
        "release_id": release_id,
        "status": "passed",
        "checks": [
            {"id": "source-contract", "status": "passed"},
            {"id": "outcome-evidence-traceability", "status": "passed"},
            {"id": "safe-lab-fields", "status": "passed"},
            {"id": "accessibility-path", "status": "passed"},
            {"id": "restricted-claims", "status": "passed"},
            {"id": "provider-neutral-outcomes", "status": "passed"},
        ],
    }
    checks_path = release_dir / "checks" / "report.json"
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_bytes(_canonical(checks))
    artifacts.append({"path": "checks/report.json", "sha256": _sha256_file(checks_path), "module_id": "program"})

    manifest = {
        "release_id": release_id,
        "program_id": program_id,
        "release_version": release_version,
        "compiler_version": COMPILER_VERSION,
        "source_digest": source_digest,
        "source_files": [path.relative_to(source_dir).as_posix() for path, _ in modules],
        "artifacts": sorted(artifacts, key=lambda item: item["path"]),
        "claims_profile": "public-launch",
        "content_status": "generated-from-reviewed-source-specifications",
        "model_dependency": "none-at-release-time",
        "human_gates": ["safety", "privacy", "accessibility", "assessment", "credential", "public-release"],
    }
    manifest_path = release_dir / "release-manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--program-id", required=True)
    parser.add_argument("--release-version", required=True)
    args = parser.parse_args()
    manifest = compile_release(args.source, args.output, args.program_id, args.release_version)
    print(f"compiled {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
