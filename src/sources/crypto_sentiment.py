"""Crypto news headlines + Fear & Greed Index (prices moved to binance_direct.py)."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

import feedparser
import httpx

_NEWS_QUERIES = [
    "cryptocurrency market today",
    "bitcoin price prediction",
    "crypto regulation news",
    "altcoin rally",
]


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []

    # Fetch Fear & Greed Index
    try:
        resp = await client.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if resp.status_code == 200:
            fng = resp.json().get("data", [{}])[0]
            val = fng.get("value", "?")
            label = fng.get("value_classification", "?")
            articles.append({
                "id": f"crypto-fng-{date.today().isoformat()}",
                "title": f"Fear & Greed Index: {val} ({label})",
                "url": "https://alternative.me/crypto/fear-and-greed-index/",
                "source": "Alternative.me",
                "points": 0,
                "published": "",
                "summary": "",
                "section": "crypto",
                "importance": 8,
                "relevance": 8,
                "one_line": f"Market sentiment: {val}/100 — {label}",
                "meta": {"fng_value": int(val) if val != "?" else 50, "fng_label": label},
            })
    except httpx.HTTPError:
        pass

    # Fetch crypto news headlines (last 24h)
    seen: set[str] = set()
    for q in _NEWS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote(q)}+when:1d&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                continue
        except httpx.HTTPError:
            continue

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            aid = f"crypto-news-{hash(entry.get('link', ''))}"
            if aid in seen:
                continue
            seen.add(aid)
            articles.append({
                "id": aid,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": "Crypto News",
                "points": 0,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
                "section": "crypto",
                "importance": 6,
                "relevance": 6,
                "one_line": entry.get("title", "")[:80],
            })

    return articles
