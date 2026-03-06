"""Real-time crypto prices from Binance public API (no auth needed)."""
from __future__ import annotations

import logging
from datetime import date

import httpx

log = logging.getLogger(__name__)

_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
    "BNBUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
]

_DISPLAY_NAMES = {
    "BTCUSDT": "Bitcoin",
    "ETHUSDT": "Ethereum",
    "SOLUSDT": "Solana",
    "XRPUSDT": "XRP",
    "BNBUSDT": "BNB",
    "ADAUSDT": "Cardano",
    "DOGEUSDT": "Dogecoin",
    "AVAXUSDT": "Avalanche",
}


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    articles: list[dict] = []

    try:
        symbols_param = "[" + ",".join(f'"{s}"' for s in _SYMBOLS) + "]"
        resp = await client.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbols": symbols_param},
            timeout=10,
        )
        if resp.status_code != 200:
            log.warning("Binance API returned %d", resp.status_code)
            return articles

        for ticker in resp.json():
            symbol = ticker["symbol"]
            name = _DISPLAY_NAMES.get(symbol, symbol.replace("USDT", ""))
            price = float(ticker["lastPrice"])
            change_pct = float(ticker["priceChangePercent"])
            high = float(ticker["highPrice"])
            low = float(ticker["lowPrice"])
            volume = float(ticker["quoteVolume"])
            arrow = "+" if change_pct >= 0 else ""

            articles.append({
                "id": f"binance-price-{symbol.lower()}-{date.today().isoformat()}",
                "title": f"{name} (${price:,.2f}) — {arrow}{change_pct:.1f}% 24h",
                "url": f"https://www.binance.com/en/trade/{symbol}",
                "source": "Binance",
                "points": 0,
                "published": "",
                "summary": "",
                "section": "crypto",
                "importance": 8,
                "relevance": 8,
                "one_line": f"${price:,.2f} ({arrow}{change_pct:.1f}% 24h) | Vol: ${volume/1e6:,.0f}M",
                "meta": {
                    "price": price,
                    "change_24h": change_pct,
                    "high_24h": high,
                    "low_24h": low,
                    "volume_24h": volume,
                },
            })

    except Exception as e:
        log.warning("Binance fetch failed: %s", e)

    return articles
