#!/usr/bin/env python3
"""Validate the SozoRock Canada static public site and clean canonical routes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path("site")
CANONICAL_ORIGIN = "https://canada.sozorock.com"
CANONICAL_PAGES = {
    "index.html": "/",
    "about.html": "/about",
    "programs.html": "/programs",
    "applied-ai.html": "/applied-ai",
    "cybersecurity-grc.html": "/cybersecurity-grc",
    "ai-governance.html": "/ai-governance",
    "cloud.html": "/cloud",
    "curriculum.html": "/curriculum",
    "enroll.html": "/enroll",
    "impact.html": "/impact",
    "contact.html": "/contact",
    "accessibility.html": "/accessibility",
    "support.html": "/support",
    "privacy.html": "/privacy",
    "terms.html": "/terms",
}
REQUIRED_PAGES = set(CANONICAL_PAGES) | {"404.html"}
CLEAN_ROUTE_FILES = {route: page for page, route in CANONICAL_PAGES.items()}


def local_target_exists(target: str) -> bool:
    clean = target.split("#", 1)[0].split("?", 1)[0]
    if clean in ("", "/"):
        return (SITE / "index.html").is_file()
    if clean.startswith("/"):
        if clean in CLEAN_ROUTE_FILES:
            return (SITE / CLEAN_ROUTE_FILES[clean]).is_file()
        return (SITE / clean.lstrip("/")).is_file()
    return (SITE / clean).is_file()


def main() -> int:
    errors: list[str] = []
    pages = {path.name for path in SITE.glob("*.html")}
    errors.extend(f"missing page: site/{name}" for name in sorted(REQUIRED_PAGES - pages))

    for retired in ("program.html", "stories.html"):
        if (SITE / retired).exists():
            errors.append(f"site/{retired} must be retired from the public architecture")

    for path in sorted(SITE.glob("*.html")):
        source = path.read_text(encoding="utf-8")
        for required in ('<html lang="en-CA">', '<meta name="viewport"', '<meta name="description"', "<title>", 'id="main"'):
            if required not in source:
                errors.append(f"{path}: missing {required}")
        if source.count("<h1") != 1:
            errors.append(f"{path}: requires exactly one h1")
        if "<form" in source.lower():
            errors.append(f"{path}: live forms are not part of the public shell")
        if 'href="#main"' not in source:
            errors.append(f"{path}: missing accessible skip link")

        fragment_links = [target for target in re.findall(r'href="([^"]+)"', source) if "#" in target and target != "#main"]
        if fragment_links:
            errors.append(f"{path}: public navigation must not use fragment URLs: {', '.join(fragment_links)}")

        if path.name in CANONICAL_PAGES:
            route = CANONICAL_PAGES[path.name]
            expected_url = f"{CANONICAL_ORIGIN}{route}"
            for required in (
                f'<link rel="canonical" href="{expected_url}">',
                f'<meta property="og:url" content="{expected_url}">',
                '<meta name="twitter:card" content="summary">',
            ):
                if required not in source:
                    errors.append(f"{path}: missing {required}")
            if "sozorock.ca" in source:
                errors.append(f"{path}: legacy .ca hostname must not appear in canonical public content")
        elif path.name == "404.html":
            if '<meta name="robots" content="noindex">' not in source:
                errors.append(f"{path}: missing noindex directive")
        else:
            errors.append(f"{path}: HTML page is not declared as canonical or 404")

        for target in re.findall(r'(?:href|src)="([^"]+)"', source):
            if target.startswith(("http:", "https:", "#", "mailto:", "tel:")):
                continue
            if not local_target_exists(target):
                errors.append(f"{path}: missing local link {target}")

    for required_asset in ("styles.css", "reference-home.css", "site.js", "favicon.svg", "robots.txt", "sitemap.xml"):
        if not (SITE / required_asset).is_file():
            errors.append(f"site/{required_asset} is missing")

    robots_path = SITE / "robots.txt"
    if robots_path.is_file():
        robots = robots_path.read_text(encoding="utf-8")
        sitemap_url = f"Sitemap: {CANONICAL_ORIGIN}/sitemap.xml"
        if sitemap_url not in robots:
            errors.append(f"site/robots.txt: missing {sitemap_url}")
        if "sozorock.ca" in robots:
            errors.append("site/robots.txt: legacy .ca hostname must not be advertised")

    sitemap_path = SITE / "sitemap.xml"
    if sitemap_path.is_file():
        sitemap = sitemap_path.read_text(encoding="utf-8")
        for route in CANONICAL_PAGES.values():
            expected_url = f"<loc>{CANONICAL_ORIGIN}{route}</loc>"
            if expected_url not in sitemap:
                errors.append(f"site/sitemap.xml: missing {expected_url}")
        if ".html</loc>" in sitemap or "/index.html</loc>" in sitemap:
            errors.append("site/sitemap.xml: HTML filenames must not be canonical URLs")
        if "/stories</loc>" in sitemap:
            errors.append("site/sitemap.xml: placeholder Stories route must not be indexed")
        if "sozorock.ca" in sitemap:
            errors.append("site/sitemap.xml: legacy .ca hostname must not be indexed")

    if errors:
        print("Static site validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Static site validation passed for {len(pages)} pages with clean canonical routes on {CANONICAL_ORIGIN}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
