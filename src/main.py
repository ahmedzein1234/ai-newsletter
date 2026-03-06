"""Daily AI Newsletter — main orchestrator."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
from datetime import date
from pathlib import Path

import httpx

from .config import settings
from .sources import ALL_FETCHERS
from . import dedup
from . import edition_store
from .curator import (
    curate,
    generate_analysis,
    generate_monetization_ideas,
    generate_uae_startup_analysis,
    generate_news_digest,
    generate_world_analysis,
    estimate_cost,
)
from .page_builder import build_daily_page, build_email, rebuild_archive_index
from .email_sender import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def _build_market_snapshot(client: httpx.AsyncClient) -> dict:
    """Fetch fresh market data directly (never deduped)."""
    snapshot: dict = {}

    # 1. Binance prices (always fresh, public API)
    try:
        symbols = '["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT"]'
        resp = await client.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbols": symbols}, timeout=10,
        )
        if resp.status_code == 200:
            snapshot["prices"] = {
                t["symbol"]: {
                    "price": float(t["lastPrice"]),
                    "change": float(t["priceChangePercent"]),
                    "volume": float(t["quoteVolume"]),
                }
                for t in resp.json()
            }
    except Exception:
        pass

    # 2. BTC Guru (local DB, always fresh)
    try:
        from .sources.btc_guru import _DB_PATH as guru_db
        if guru_db.exists():
            conn = sqlite3.connect(str(guru_db))
            conn.row_factory = sqlite3.Row
            snap = dict(conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone())
            pred = conn.execute(
                "SELECT * FROM predictions WHERE snapshot_id=? AND scored_at IS NULL ORDER BY id DESC LIMIT 1",
                (snap["id"],),
            ).fetchone()
            pred = dict(pred) if pred else {}
            conn.close()
            snapshot["btc_guru"] = {
                "ensemble": snap.get("ensemble_score"),
                "regime": snap.get("regime"),
                "rsi_1h": snap.get("rsi_1h"),
                "rsi_4h": snap.get("rsi_4h"),
                "macd_hist": snap.get("macd_hist"),
                "trend_1h": snap.get("trend_1h"),
                "trend_4h": snap.get("trend_4h"),
                "trend_1d": snap.get("trend_1d"),
                "fear_greed": snap.get("fear_greed_value"),
                "fng_label": snap.get("fear_greed_label"),
                "funding_rate": snap.get("funding_rate"),
                "open_interest": snap.get("open_interest"),
                "long_short_ratio": snap.get("long_short_ratio"),
                "gold_price": snap.get("gold_price"),
                "gold_change_pct": snap.get("gold_change_pct"),
                "vix": snap.get("vix"),
                "sp500_change": snap.get("sp500_change_pct"),
                "direction": pred.get("direction", "NEUTRAL"),
                "confidence": pred.get("confidence", 0),
                "target": pred.get("target_price", 0),
            }
    except Exception:
        pass

    # 3. Pulse Trader (local DB, always fresh)
    try:
        from .sources.pulse_trader_db import _DB_PATH as pt_db
        if pt_db.exists():
            conn = sqlite3.connect(str(pt_db))
            conn.row_factory = sqlite3.Row
            open_pos = [dict(r) for r in conn.execute(
                "SELECT symbol, strategy, entry_price, current_price, unrealized_pnl_pct "
                "FROM positions WHERE status='open'"
            ).fetchall()]
            recent = [dict(r) for r in conn.execute(
                "SELECT symbol, strategy, realized_pnl FROM positions "
                "WHERE status='closed' AND closed_at > datetime('now','-24 hours')"
            ).fetchall()]
            stats = conn.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT 1").fetchone()
            stats = dict(stats) if stats else {}
            conn.close()
            snapshot["pulse_trader"] = {
                "open_positions": [
                    {"symbol": p["symbol"], "strategy": p["strategy"], "entry": p["entry_price"]}
                    for p in open_pos
                ],
                "open_count": len(open_pos),
                "closed_24h": len(recent),
                "wins": sum(1 for r in recent if r.get("realized_pnl", 0) > 0),
                "losses": sum(1 for r in recent if r.get("realized_pnl", 0) <= 0),
                "pnl_usdt": round(sum(r.get("realized_pnl", 0) for r in recent), 2),
                "daily_pnl_pct": stats.get("total_pnl_pct", 0),
            }
    except Exception:
        pass

    # 4. Fear & Greed (public API, always fresh)
    try:
        resp = await client.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if resp.status_code == 200:
            fng = resp.json().get("data", [{}])[0]
            snapshot["fear_greed"] = {
                "value": int(fng.get("value", 50)),
                "label": fng.get("value_classification", "?"),
            }
    except Exception:
        pass

    return snapshot


async def run() -> None:
    today = date.today()
    log.info("Newsletter run for %s (dry_run=%s)", today, settings.dry_run)

    # 1. Fetch from all sources in parallel + build market snapshot
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [fetcher(client) for _, fetcher in ALL_FETCHERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        market_snapshot = await _build_market_snapshot(client)

    log.info("Market snapshot keys: %s", list(market_snapshot.keys()))

    all_articles: list[dict] = []
    for (name, _), result in zip(ALL_FETCHERS, results):
        if isinstance(result, Exception):
            log.warning("Source %s failed: %s", name, result)
            continue
        log.info("Source %s: %d articles", name, len(result))
        all_articles.extend(result)

    log.info("Total raw articles: %d", len(all_articles))

    # 2. Deduplicate
    store = dedup.load()
    store = dedup.prune(store)
    new_articles = dedup.filter_new(all_articles, store)
    log.info("New (unsent) articles: %d", len(new_articles))

    if not new_articles:
        log.info("No new articles, nothing to send")
        return

    # 3. LLM curation
    curated = await curate(new_articles)
    log.info("After curation: %d articles", len(curated))

    if not curated:
        log.info("Nothing passed curation, skipping")
        return

    # 3b. Load previous editions for context
    prev_editions = edition_store.load_previous(n=3)
    prev_context = edition_store.get_context_prompt(prev_editions)
    log.info("Previous editions loaded: %d", len(prev_editions))

    # 3c. Generate all analyses in parallel
    analysis_task = generate_analysis(curated, market_snapshot=market_snapshot, prev_context=prev_context)
    monetization_task = generate_monetization_ideas(curated)
    uae_task = generate_uae_startup_analysis(curated)
    digest_task = generate_news_digest(curated, prev_context=prev_context)
    world_task = generate_world_analysis(curated)

    analysis, monetization_ideas, uae_analysis, news_digest, world_analysis = (
        await asyncio.gather(
            analysis_task, monetization_task, uae_task, digest_task, world_task,
        )
    )

    log.info(
        "Generated: analysis=%d, monetization=%d, uae=%d, digest=%d, world=%d chars",
        len(analysis), len(monetization_ideas), len(uae_analysis),
        len(news_digest), len(world_analysis),
    )

    # 3f. Cost tracking
    cost_info = estimate_cost()
    total_read_time = sum(a.get("read_time", 2) for a in curated)
    log.info("Cost: $%.4f (%d LLM calls), Total read time: %d min", cost_info["est_cost_usd"], cost_info["llm_calls"], total_read_time)

    # 4. Build static page
    page_path = build_daily_page(
        curated, today,
        analysis=analysis,
        monetization_ideas=monetization_ideas,
        uae_analysis=uae_analysis,
        news_digest=news_digest,
        world_analysis=world_analysis,
        cost_info=cost_info,
        total_read_time=total_read_time,
        market_snapshot=market_snapshot,
    )
    rebuild_archive_index()
    log.info("Page built: %s", page_path)

    # 5. Build and send email
    email_html = build_email(
        curated, today,
        analysis=analysis,
        monetization_ideas=monetization_ideas,
        uae_analysis=uae_analysis,
        news_digest=news_digest,
        world_analysis=world_analysis,
        cost_info=cost_info,
        total_read_time=total_read_time,
        market_snapshot=market_snapshot,
    )
    subject = f"Zein's AI Newsletter \u2014 {today.strftime('%b %d, %Y').replace(' 0', ' ')}"

    if settings.dry_run:
        log.info("DRY RUN: would send email '%s' with %d articles", subject, len(curated))
        # Write preview
        preview_path = f"site/{today.isoformat()}/email_preview.html"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(email_html)
        log.info("Email preview saved: %s", preview_path)
    else:
        sent = await send_email(subject, email_html)
        if sent:
            log.info("Email sent successfully")
        else:
            log.error("Email delivery failed")

    # 6. Mark articles as sent
    store = dedup.mark_sent(curated, store)
    dedup.save(store)
    log.info("Dedup store updated with %d articles", len(curated))

    # 7. Save edition summary for cross-edition context
    edition_store.save_edition(today, curated, analysis)
    log.info("Edition summary saved")


def main() -> None:
    if "--dry-run" in sys.argv:
        settings.dry_run = True
    asyncio.run(run())


if __name__ == "__main__":
    main()
