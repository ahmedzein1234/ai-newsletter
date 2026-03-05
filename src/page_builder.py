"""Build static HTML pages for Cloudflare Pages."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import settings


def _env() -> Environment:
    template_dir = Path(__file__).parent / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)


def build_daily_page(articles: list[dict], today: date) -> str:
    env = _env()
    tmpl = env.get_template("page.html")

    sections = _group_sections(articles)
    html = tmpl.render(date=today.isoformat(), sections=sections, site_url=settings.site_url)

    out_dir = Path(settings.site_dir) / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def build_email(articles: list[dict], today: date) -> str:
    env = _env()
    tmpl = env.get_template("email.html")

    sections = _group_sections(articles)
    page_url = f"{settings.site_url}/{today.isoformat()}/"
    return tmpl.render(date=today.isoformat(), sections=sections, page_url=page_url)


def rebuild_archive_index() -> None:
    site = Path(settings.site_dir)
    editions = sorted(
        [d.name for d in site.iterdir() if d.is_dir() and d.name[:2] == "20"],
        reverse=True,
    )

    items_html = "\n".join(
        f'<li><a href="{e}/">{e}</a></li>' for e in editions
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Newsletter Archive</title>
<link rel="stylesheet" href="style.css">
</head><body>
<div class="container">
<h1>AI Newsletter Archive</h1>
<p>Daily curated AI news — Claude Code, AI tools, monetization.</p>
<ul class="archive-list">{items_html}</ul>
</div>
</body></html>"""

    (site / "index.html").write_text(html, encoding="utf-8")


_SECTION_TITLES = {
    "claude": "Claude Code & MCP",
    "tools": "AI Tools & APIs",
    "monetization": "Monetization",
    "projects": "Project-Relevant",
    "links": "Quick Links",
}


def _group_sections(articles: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for a in articles:
        sec = a.get("section", "links")
        groups.setdefault(sec, []).append(a)

    order = ["claude", "tools", "monetization", "projects", "links"]
    out = []
    for key in order:
        items = groups.get(key, [])
        if items:
            out.append({"key": key, "title": _SECTION_TITLES.get(key, key), "entries": items})
    return out
