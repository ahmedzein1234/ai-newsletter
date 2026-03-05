"""Gold price and quant/algo trading news (free, no auth)."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

import feedparser
import httpx

_NEWS_QUERIES = [
    "gold price forecast",
    "gold market analysis",
    "quantitative trading",
    "algorithmic trading strategy",
]

_SUBREDDITS = ["algotrading", "quant"]
_GOLD_API = "https://api.coingecko.com/api/v3/simple/price"


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []

    # Gold price via CoinGecko (tracks XAU via paxg as proxy)
    try:
        resp = await client.get(
            _GOLD_API,
            params={"ids": "pax-gold", "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("pax-gold", {})
            price = data.get("usd", 0)
            change = data.get("usd_24h_change", 0) or 0
            arrow = "+" if change >= 0 else ""
            articles.append({
                "id": "gold-price-today",
                "title": f"Gold (PAXG proxy): ${price:,.2f} ({arrow}{change:.1f}% 24h)",
                "url": "https://www.coingecko.com/en/coins/pax-gold",
                "source": "CoinGecko",
                "points": 0,
                "published": "",
                "summary": "",
                "section": "gold_quant",
                "relevance": 8,
                "one_line": f"Gold ~${price:,.0f} ({arrow}{change:.1f}% 24h)",
                "meta": {"gold_price": price, "gold_change_24h": change},
            })
    except httpx.HTTPError:
        pass

    # Google News for gold + quant trading
    seen: set[str] = set()
    for q in _NEWS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                continue
        except httpx.HTTPError:
            continue

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            aid = f"goldquant-{hash(entry.get('link', ''))}"
            if aid in seen:
                continue
            seen.add(aid)
            articles.append({
                "id": aid,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": "Gold/Quant News",
                "points": 0,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
                "section": "gold_quant",
                "relevance": 6,
                "one_line": entry.get("title", "")[:80],
            })

    # Reddit r/algotrading and r/quant
    for sub in _SUBREDDITS:
        rss_url = f"https://www.reddit.com/r/{sub}/hot.rss?limit=10"
        try:
            resp = await client.get(rss_url, headers={"User-Agent": "ai-newsletter/1.0"}, timeout=15)
            if resp.status_code != 200:
                continue
        except httpx.HTTPError:
            continue

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            aid = f"goldquant-reddit-{entry.get('id', entry.link)}"
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
                "section": "gold_quant",
                "relevance": 5,
                "one_line": entry.get("title", "")[:80],
            })

    return articles
