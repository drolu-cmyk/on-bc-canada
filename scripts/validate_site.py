#!/usr/bin/env python3
"""Validate the static public information shell."""

from __future__ import annotations

import re
import sys
from pathlib import Path


SITE = Path("site")
CANONICAL_ORIGIN = "https://www.sozorock.ca"
CONTENT_PAGES = {
    "index.html",
    "program.html",
    "curriculum.html",
    "enroll.html",
    "accessibility.html",
    "support.html",
    "privacy.html",
    "terms.html",
}
REQUIRED_PAGES = CONTENT_PAGES | {"404.html"}


def canonical_path(page_name: str) -> str:
    return "/" if page_name == "index.html" else f"/{page_name}"


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

        if path.name in CONTENT_PAGES:
            expected_url = f"{CANONICAL_ORIGIN}{canonical_path(path.name)}"
            required_metadata = (
                f'<link rel="canonical" href="{expected_url}">',
                f'<meta property="og:url" content="{expected_url}">',
                '<meta name="twitter:card" content="summary">',
            )
            for required in required_metadata:
                if required not in source:
                    errors.append(f"{path}: missing {required}")
        elif '<meta name="robots" content="noindex">' not in source:
            errors.append(f"{path}: missing noindex directive")

        for target in re.findall(r'(?:href|src)="([^"]+)"', source):
            if target.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target_path = path.parent / target.split("#", 1)[0]
            if not target_path.exists():
                errors.append(f"{path}: missing local link {target}")

    if not (SITE / "styles.css").is_file():
        errors.append("site/styles.css is missing")
    robots_path = SITE / "robots.txt"
    if not robots_path.is_file():
        errors.append("site/robots.txt is missing")
    else:
        robots = robots_path.read_text(encoding="utf-8")
        sitemap_url = f"Sitemap: {CANONICAL_ORIGIN}/sitemap.xml"
        if sitemap_url not in robots:
            errors.append(f"site/robots.txt: missing {sitemap_url}")

    sitemap_path = SITE / "sitemap.xml"
    if not sitemap_path.is_file():
        errors.append("site/sitemap.xml is missing")
    else:
        sitemap = sitemap_path.read_text(encoding="utf-8")
        for page_name in sorted(CONTENT_PAGES):
            expected_url = f"<loc>{CANONICAL_ORIGIN}{canonical_path(page_name)}</loc>"
            if expected_url not in sitemap:
                errors.append(f"site/sitemap.xml: missing {expected_url}")

    if errors:
        print("Static site validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Static site validation passed for {len(pages)} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
