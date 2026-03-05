"""Reddit via public RSS feeds (free, no auth)."""
from __future__ import annotations

import feedparser
import httpx

_SUBREDDITS = [
    "ClaudeAI",
    "MachineLearning",
    "artificial",
    "LocalLLaMA",
]

_HEADERS = {"User-Agent": "ai-newsletter/1.0"}


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []
    seen: set[str] = set()

    for sub in _SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/hot.rss?limit=20"
        try:
            resp = await client.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
        except httpx.HTTPError:
            continue

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:15]:
            aid = f"reddit-{entry.get('id', entry.link)}"
            if aid in seen:
                continue
            seen.add(aid)
            articles.append({
                "id": aid,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": f"r/{sub}",
                "points": 0,
                "published": entry.get("published", ""),
                "summary": "",
            })

    return articles[:30]
