"""Dev.to articles via public API (free, no auth)."""
from __future__ import annotations

import asyncio

import httpx

_TAGS = ["ai", "machinelearning", "llm", "claude", "openai"]
_BASE = "https://dev.to/api/articles"


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    async def _by_tag(tag: str) -> list[dict]:
        params = {"tag": tag, "per_page": 10, "top": 1}
        try:
            resp = await client.get(_BASE, params=params, timeout=15)
            if resp.status_code != 200:
                return []
        except httpx.HTTPError:
            return []

        out = []
        for a in resp.json()[:10]:
            out.append({
                "id": f"devto-{a['id']}",
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": "Dev.to",
                "points": a.get("positive_reactions_count", 0),
                "published": a.get("published_at", ""),
                "summary": a.get("description", ""),
            })
        return out

    results = await asyncio.gather(*[_by_tag(t) for t in _TAGS])
    for batch in results:
        for a in batch:
            if a["id"] not in seen:
                seen.add(a["id"])
                articles.append(a)

    articles.sort(key=lambda x: x.get("points", 0), reverse=True)
    return articles[:20]
