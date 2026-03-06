"""BTC Guru analysis from local SQLite database (read-only)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_DB_PATH = Path(r"C:\Users\amzei\Documents\btc gurru\data\btc_gurru.db")


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    """Read latest BTC Guru snapshot and predictions. Client arg unused (local DB)."""
    articles: list[dict] = []

    if not _DB_PATH.exists():
        log.warning("BTC Guru DB not found at %s", _DB_PATH)
        return articles

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row

        # Latest snapshot
        row = conn.execute(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            conn.close()
            return articles

        snap = dict(row)
        snapshot_id = snap["id"]

        # Latest unscored prediction
        pred_row = conn.execute(
            "SELECT * FROM predictions WHERE snapshot_id = ? AND scored_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        pred = dict(pred_row) if pred_row else {}

        # Recent accuracy
        acc_row = conn.execute(
            "SELECT * FROM daily_accuracy ORDER BY date DESC LIMIT 1"
        ).fetchone()
        acc = dict(acc_row) if acc_row else {}

        conn.close()

        direction = pred.get("direction", "NEUTRAL")
        confidence = pred.get("confidence", 0)
        target_price = pred.get("target_price", 0)
        regime = snap.get("regime", "unknown")
        regime_conf = snap.get("regime_confidence", 0)

        title = f"BTC Guru: {direction} ({confidence:.0f}% conf) — Regime: {regime}"

        meta = {
            "technical_score": snap.get("technical_score"),
            "sentiment_score": snap.get("sentiment_score"),
            "onchain_score": snap.get("onchain_score"),
            "ensemble_score": snap.get("ensemble_score"),
            "derivatives_score": snap.get("derivatives_score"),
            "regime": regime,
            "regime_confidence": regime_conf,
            "btc_price": snap.get("price"),
            "rsi_1h": snap.get("rsi_1h"),
            "rsi_4h": snap.get("rsi_4h"),
            "macd_hist": snap.get("macd_hist"),
            "trend_1h": snap.get("trend_1h"),
            "trend_4h": snap.get("trend_4h"),
            "trend_1d": snap.get("trend_1d"),
            "fear_greed_value": snap.get("fear_greed_value"),
            "fear_greed_label": snap.get("fear_greed_label"),
            "vix": snap.get("vix"),
            "sp500_change_pct": snap.get("sp500_change_pct"),
            "gold_price": snap.get("gold_price"),
            "gold_change_pct": snap.get("gold_change_pct"),
            "funding_rate": snap.get("funding_rate"),
            "open_interest": snap.get("open_interest"),
            "long_short_ratio": snap.get("long_short_ratio"),
            "prediction_direction": direction,
            "prediction_confidence": confidence,
            "prediction_target": target_price,
        }

        if acc:
            meta["accuracy_pct"] = acc.get("direction_accuracy_pct")
            meta["total_predictions"] = acc.get("total_predictions")

        one_line = (
            f"Ensemble: {snap.get('ensemble_score', 0):.1f} | "
            f"RSI 1h: {snap.get('rsi_1h', 0):.0f} | "
            f"F&G: {snap.get('fear_greed_value', '?')} ({snap.get('fear_greed_label', '?')}) | "
            f"Target: ${target_price:,.0f}"
        )

        articles.append({
            "id": f"btc-guru-{snapshot_id}",
            "title": title,
            "url": "https://www.binance.com/en/trade/BTCUSDT",
            "source": "BTC Guru (Local)",
            "points": 0,
            "published": snap.get("timestamp", ""),
            "summary": "",
            "section": "crypto",
            "importance": 9,
            "relevance": 9,
            "one_line": one_line,
            "meta": meta,
        })

    except Exception as e:
        log.warning("BTC Guru fetch failed: %s", e)

    return articles
