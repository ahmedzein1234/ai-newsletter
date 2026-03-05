"""Hacker News via Algolia API (free, no auth)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

_QUERIES = [
    "claude code",
    "anthropic",
    "AI tools",
    "MCP server",
    "AI monetization",
]

_BASE = "https://hn.algolia.com/api/v1/search_by_date"


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []

    async def _query(q: str) -> list[dict]:
        params = {
            "query": q,
            "tags": "story",
            "numericFilters": "points>5",
            "hitsPerPage": 15,
        }
        resp = await client.get(_BASE, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits", [])
        out = []
        for h in hits:
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append({
                "id": f"hn-{h['objectID']}",
                "title": h.get("title", ""),
                "url": url,
                "source": "Hacker News",
                "points": h.get("points", 0),
                "published": h.get("created_at", ""),
                "summary": "",
            })
        return out

    results = await asyncio.gather(*[_query(q) for q in _QUERIES])
    seen_ids: set[str] = set()
    for batch in results:
        for a in batch:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                articles.append(a)

    articles.sort(key=lambda x: x.get("points", 0), reverse=True)
    return articles[:30]
