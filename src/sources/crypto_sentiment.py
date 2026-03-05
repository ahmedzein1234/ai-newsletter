"""Crypto market data from CoinGecko + news from Google News RSS (free, no auth)."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

import feedparser
import httpx

_TOP_COINS = ["bitcoin", "ethereum", "solana", "xrp", "bnb", "cardano", "dogecoin", "avalanche"]
_COINGECKO_URL = "https://api.coingecko.com/api/v3"
_NEWS_QUERIES = [
    "cryptocurrency market today",
    "bitcoin price prediction",
    "crypto regulation news",
    "altcoin rally",
]


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []

    # Fetch top coin prices
    try:
        resp = await client.get(
            f"{_COINGECKO_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(_TOP_COINS),
                "order": "market_cap_desc",
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            for coin in resp.json():
                change_24h = coin.get("price_change_percentage_24h", 0) or 0
                change_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
                arrow = "+" if change_24h >= 0 else ""
                articles.append({
                    "id": f"crypto-price-{coin['id']}",
                    "title": f"{coin['name']} (${coin.get('current_price', 0):,.2f}) — {arrow}{change_24h:.1f}% 24h",
                    "url": f"https://www.coingecko.com/en/coins/{coin['id']}",
                    "source": "CoinGecko",
                    "points": 0,
                    "published": "",
                    "summary": "",
                    "section": "crypto",
                    "relevance": 7,
                    "one_line": f"${coin.get('current_price', 0):,.2f} ({arrow}{change_24h:.1f}% 24h)",
                    "meta": {
                        "price": coin.get("current_price", 0),
                        "change_24h": change_24h,
                        "change_7d": change_7d,
                        "market_cap": coin.get("market_cap", 0),
                        "volume_24h": coin.get("total_volume", 0),
                    },
                })
    except httpx.HTTPError:
        pass

    # Fetch Fear & Greed Index
    try:
        resp = await client.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if resp.status_code == 200:
            fng = resp.json().get("data", [{}])[0]
            val = fng.get("value", "?")
            label = fng.get("value_classification", "?")
            articles.append({
                "id": "crypto-fng-today",
                "title": f"Fear & Greed Index: {val} ({label})",
                "url": "https://alternative.me/crypto/fear-and-greed-index/",
                "source": "Alternative.me",
                "points": 0,
                "published": "",
                "summary": "",
                "section": "crypto",
                "relevance": 8,
                "one_line": f"Market sentiment: {val}/100 — {label}",
                "meta": {"fng_value": int(val) if val != "?" else 50, "fng_label": label},
            })
    except httpx.HTTPError:
        pass

    # Fetch crypto news headlines
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
                "relevance": 6,
                "one_line": entry.get("title", "")[:80],
            })

    return articles
