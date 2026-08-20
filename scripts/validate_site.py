#!/usr/bin/env python3
"""Validate the static public information shell."""

from __future__ import annotations

import re
import sys
from pathlib import Path


SITE = Path("site")
REQUIRED_PAGES = {
    "index.html",
    "program.html",
    "curriculum.html",
    "enroll.html",
    "accessibility.html",
    "support.html",
    "privacy.html",
    "terms.html",
    "404.html",
}


def main() -> int:
    errors: list[str] = []
    pages = {path.name for path in SITE.glob("*.html")}
    errors.extend(f"missing page: site/{name}" for name in sorted(REQUIRED_PAGES - pages))

    for path in sorted(SITE.glob("*.html")):
        source = path.read_text(encoding="utf-8")
        for required in (
            '<html lang="en-CA">',
            '<meta name="viewport"',
            '<meta name="description"',
            "<title>",
            'id="main"',
        ):
            if required not in source:
                errors.append(f"{path}: missing {required}")
        if source.count("<h1") != 1:
            errors.append(f"{path}: requires exactly one h1")
        if "<form" in source.lower():
            errors.append(f"{path}: live forms are not part of the public shell")
        if path.name != "404.html" and 'href="#main"' not in source:
            errors.append(f"{path}: missing skip link")

        for target in re.findall(r'(?:href|src)="([^"]+)"', source):
            if target.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target_path = path.parent / target.split("#", 1)[0]
            if not target_path.exists():
                errors.append(f"{path}: missing local link {target}")

    if not (SITE / "styles.css").is_file():
        errors.append("site/styles.css is missing")
    if not (SITE / "robots.txt").is_file():
        errors.append("site/robots.txt is missing")

    if errors:
        print("Static site validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Static site validation passed for {len(pages)} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
