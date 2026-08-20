#!/usr/bin/env python3
"""Reject advisory and internal planning vocabulary from public copy."""

from __future__ import annotations

import re
import sys
from pathlib import Path


PUBLIC_FILES = [
    Path("README.md"),
    Path("PROGRAM_CHARTER.md"),
    Path("CAPABILITY_DOMAINS.md"),
    Path("CONTRIBUTING.md"),
    Path("compiler/README.md"),
    Path("runtime/README.md"),
    *sorted(Path("docs").glob("*.md")),
    *sorted(Path("site").glob("*.html")),
    *sorted(Path("config").glob("*.yaml")),
    *sorted(Path("policies").glob("*.yaml")),
    *sorted(Path("content/modules").glob("*.yaml")),
]


BANNED_TERMS = {
    "advisory": re.compile(r"\badvisory\b", re.IGNORECASE),
    "could": re.compile(r"\bcould\b", re.IGNORECASE),
    "draft": re.compile(r"\bdraft\b", re.IGNORECASE),
    "future": re.compile(r"\bfuture\b", re.IGNORECASE),
    "intended": re.compile(r"\bintended\b", re.IGNORECASE),
    "internal": re.compile(r"\binternal\b", re.IGNORECASE),
    "may": re.compile(r"\bmay\b", re.IGNORECASE),
    "might": re.compile(r"\bmight\b", re.IGNORECASE),
    "mvp": re.compile(r"\bmvp\b", re.IGNORECASE),
    "pending": re.compile(r"\bpending\b", re.IGNORECASE),
    "planned": re.compile(r"\bplanned\b", re.IGNORECASE),
    "planning": re.compile(r"\bplanning\b", re.IGNORECASE),
    "proposed": re.compile(r"\bproposed\b", re.IGNORECASE),
    "recommend": re.compile(r"\brecommend(?:ed|ation)?\b", re.IGNORECASE),
    "roadmap": re.compile(r"\broadmap\b", re.IGNORECASE),
    "should": re.compile(r"\bshould\b", re.IGNORECASE),
    "target": re.compile(r"\btarget\b", re.IGNORECASE),
    "todo": re.compile(r"\btodo\b", re.IGNORECASE),
    "tbd": re.compile(r"\btbd\b", re.IGNORECASE),
}


def main() -> int:
    violations: list[str] = []
    for path in PUBLIC_FILES:
        if not path.is_file():
            violations.append(f"missing public file: {path}")
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, pattern in BANNED_TERMS.items():
                if pattern.search(line):
                    violations.append(f"{path}:{line_number}: banned public-copy term '{label}'")

    if violations:
        print("Public-copy validation failed:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1

    print(f"Public-copy validation passed for {len(PUBLIC_FILES)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
