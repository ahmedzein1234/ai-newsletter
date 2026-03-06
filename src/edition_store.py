"""Save and load daily edition summaries for cross-edition context."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_EDITIONS_DIR = Path("data/editions")


def save_edition(today: date, articles: list[dict], analysis: str) -> None:
    _EDITIONS_DIR.mkdir(parents=True, exist_ok=True)

    section_counts: dict[str, int] = {}
    for a in articles:
        sec = a.get("section", "quick_links")
        section_counts[sec] = section_counts.get(sec, 0) + 1

    top_headlines = [
        a.get("editorial_title", a.get("title", ""))
        for a in sorted(articles, key=lambda x: x.get("importance", 0), reverse=True)[:10]
    ]

    edition = {
        "date": today.isoformat(),
        "article_count": len(articles),
        "section_counts": section_counts,
        "top_headlines": top_headlines,
        "analysis_summary": analysis[:500] if analysis else "",
    }

    path = _EDITIONS_DIR / f"{today.isoformat()}.json"
    path.write_text(json.dumps(edition, indent=2), encoding="utf-8")
    log.info("Edition saved: %s", path)


def load_previous(n: int = 3) -> list[dict]:
    if not _EDITIONS_DIR.exists():
        return []

    files = sorted(_EDITIONS_DIR.glob("*.json"), reverse=True)
    editions = []
    for f in files[:n]:
        try:
            editions.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("Failed to load edition %s: %s", f, e)

    return editions


def get_context_prompt(editions: list[dict]) -> str:
    if not editions:
        return ""

    parts = ["## Previous Editions (for cross-edition context — avoid repeating these):\n"]
    for ed in editions:
        parts.append(f"### {ed['date']} ({ed['article_count']} articles)")
        parts.append(f"Sections: {json.dumps(ed.get('section_counts', {}))}")
        headlines = ed.get("top_headlines", [])
        if headlines:
            parts.append("Top headlines: " + " | ".join(headlines[:5]))
        summary = ed.get("analysis_summary", "")
        if summary:
            parts.append(f"Analysis: {summary[:200]}")
        parts.append("")

    return "\n".join(parts)
