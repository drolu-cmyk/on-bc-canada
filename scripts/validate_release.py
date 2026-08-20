#!/usr/bin/env python3
"""Validate a generated release manifest and the hashes it references."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/release-manifest.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "root"
            print(f"ERROR manifest {location}: {error.message}")
        return 1

    release_root = manifest_path.parent
    for artifact in manifest["artifacts"]:
        artifact_path = release_root / artifact["path"]
        if not artifact_path.is_file():
            print(f"ERROR manifest missing artifact: {artifact['path']}")
            return 1
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            print(f"ERROR manifest hash mismatch: {artifact['path']}")
            return 1
    print(f"OK    release manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
