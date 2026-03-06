"""Pulse Trader bot status from local SQLite database (read-only)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_DB_PATH = Path(r"C:\Users\amzei\Documents\pulse-trader\data\pulse_trader.db")


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    """Read Pulse Trader open positions and daily stats. Client arg unused (local DB)."""
    articles: list[dict] = []

    if not _DB_PATH.exists():
        log.warning("Pulse Trader DB not found at %s", _DB_PATH)
        return articles

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row

        # Open positions
        open_positions = conn.execute(
            "SELECT * FROM positions WHERE status = 'open'"
        ).fetchall()
        open_positions = [dict(r) for r in open_positions]

        # Recently closed (last 24h)
        recent_closed = conn.execute(
            "SELECT * FROM positions WHERE status = 'closed' "
            "AND closed_at > datetime('now', '-24 hours')"
        ).fetchall()
        recent_closed = [dict(r) for r in recent_closed]

        # Latest daily stats
        stats_row = conn.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT 1"
        ).fetchone()
        stats = dict(stats_row) if stats_row else {}

        conn.close()

        open_count = len(open_positions)
        closed_today = len(recent_closed)
        wins = sum(1 for p in recent_closed if p.get("realized_pnl", 0) > 0)
        losses = closed_today - wins
        total_pnl = sum(p.get("realized_pnl", 0) for p in recent_closed)

        daily_pnl_pct = stats.get("total_pnl_pct", 0) or 0
        pnl_arrow = "+" if daily_pnl_pct >= 0 else ""

        title = f"Pulse Trader: {open_count} open | 24h: {wins}W/{losses}L | P&L: {pnl_arrow}{daily_pnl_pct:.2f}%"

        # Build open positions summary
        pos_summary = []
        for p in open_positions:
            sym = p.get("symbol", "?")
            strat = p.get("strategy", "?")
            entry = p.get("entry_price", 0)
            pos_summary.append(f"{sym} ({strat}) @ ${entry:,.4f}")

        meta = {
            "open_count": open_count,
            "closed_today": closed_today,
            "wins_today": wins,
            "losses_today": losses,
            "total_pnl_usdt": round(total_pnl, 2),
            "daily_pnl_pct": daily_pnl_pct,
            "max_drawdown_pct": stats.get("max_drawdown_pct", 0),
            "best_trade_pct": stats.get("best_trade_pct", 0),
            "worst_trade_pct": stats.get("worst_trade_pct", 0),
            "open_positions": pos_summary[:5],
        }

        one_line = (
            f"{open_count} open positions | "
            f"24h: {wins}W/{losses}L, ${total_pnl:+.2f} USDT"
        )

        articles.append({
            "id": f"pulse-trader-daily-{stats.get('date', 'today')}",
            "title": title,
            "url": "http://localhost:8501",
            "source": "Pulse Trader (Local)",
            "points": 0,
            "published": "",
            "summary": "",
            "section": "crypto",
            "importance": 7,
            "relevance": 7,
            "one_line": one_line,
            "meta": meta,
        })

    except Exception as e:
        log.warning("Pulse Trader fetch failed: %s", e)

    return articles
