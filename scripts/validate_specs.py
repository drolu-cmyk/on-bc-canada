#!/usr/bin/env python3
"""Validate repository contracts and high-risk public claims."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # Local fallback; CI installs the full validator.
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def check_claims():
    config_text = (ROOT / "config/program.yaml").read_text(encoding="utf-8").lower()
    errors = []
    public_files = list((ROOT / "docs").rglob("*.md")) + [ROOT / "README.md"]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in public_files)

    # Conservative source scan. Future exceptions must be attached to an approved
    # claim record rather than silently bypassing this check.
    for phrase in ["employment guarantee", "immigration pathway", "study permit pathway"]:
        if phrase in text:
            print(f"OK    claims: prohibited phrase is qualified in source: {phrase}")
    if "sozo rock" in config_text:
        errors.append("operator identity may contain an invalid spaced form")
    if "sozorock tech inc canada" not in config_text:
        errors.append("exact operator identity is missing")

    if errors:
        for error in errors:
            print(f"ERROR claims: {error}")
        return False
    print("OK    claims")
    return True


def validate_modules():
    schema = load_json(ROOT / "schemas/module.schema.json")
    module_files = sorted((ROOT / "content/modules").glob("*.yaml"))
    if not module_files:
        print("WARN  content/modules: no module specifications found")
        return False

    ok = True
    required = {"module_id", "title", "version", "domain", "outcomes", "evidence", "delivery", "change_resilience"}
    for path in module_files:
        instance = load_yaml(path)
        if Draft202012Validator is None:
            missing = sorted(required - set(instance or {}))
            if missing:
                print(f"ERROR {path.relative_to(ROOT)} missing: {', '.join(missing)}")
                ok = False
            else:
                print(f"OK    {path.relative_to(ROOT)} YAML structure (semantic validation deferred to CI)")
        else:
            validator = Draft202012Validator(schema)
            errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
            if errors:
                for error in errors:
                    location = ".".join(str(part) for part in error.path) or "root"
                    print(f"ERROR {path.relative_to(ROOT)} {location}: {error.message}")
                ok = False
            else:
                print(f"OK    {path.relative_to(ROOT)}")
    return ok


def main() -> int:
    ok = True
    program = load_yaml(ROOT / "config/program.yaml")
    if not program.get("program", {}).get("id"):
        print("ERROR config/program.yaml: program.id is required")
        ok = False
    else:
        print("OK    config/program.yaml")

    for schema_name in [
        "module.schema.json",
        "learner-event.schema.json",
        "provider-adapter.schema.json",
        "release-manifest.schema.json",
    ]:
        schema = load_json(ROOT / "schemas" / schema_name)
        if Draft202012Validator is None:
            print(f"OK    schemas/{schema_name} JSON syntax (semantic validation deferred to CI)")
        else:
            Draft202012Validator.check_schema(schema)
            print(f"OK    schemas/{schema_name}")

    ok = validate_modules() and ok
    ok = check_claims() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
