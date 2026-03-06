"""World news & geopolitics via Google News RSS feeds (last 24h)."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

import feedparser
import httpx

_QUERIES = [
    "world news today",
    "breaking news international",
    "geopolitics news",
    "middle east news",
]

_BASE = "https://news.google.com/rss/search?q={query}+when:1d&hl=en-US&gl=US&ceid=US:en"


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    async def _query(q: str) -> list[dict]:
        url = _BASE.format(query=quote(q))
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                return []
        except httpx.HTTPError:
            return []

        feed = feedparser.parse(resp.text)
        out = []
        for entry in feed.entries[:8]:
            out.append({
                "id": f"gnews-world-{hash(entry.get('link', ''))}",
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": "World News",
                "points": 0,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            })
        return out

    results = await asyncio.gather(*[_query(q) for q in _QUERIES])
    for batch in results:
        for a in batch:
            if a["id"] not in seen:
                seen.add(a["id"])
                articles.append(a)

    return articles[:20]
