"""Daily AI Newsletter — main orchestrator."""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

import httpx

from .config import settings
from .sources import ALL_FETCHERS
from . import dedup
from .curator import curate
from .page_builder import build_daily_page, build_email, rebuild_archive_index
from .email_sender import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def run() -> None:
    today = date.today()
    log.info("Newsletter run for %s (dry_run=%s)", today, settings.dry_run)

    # 1. Fetch from all sources in parallel
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [fetcher(client) for _, fetcher in ALL_FETCHERS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

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

    # 4. Build static page
    page_path = build_daily_page(curated, today)
    rebuild_archive_index()
    log.info("Page built: %s", page_path)

    # 5. Build and send email
    email_html = build_email(curated, today)
    subject = f"AI Daily Brief — {today.isoformat()}"

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


def main() -> None:
    if "--dry-run" in sys.argv:
        settings.dry_run = True
    asyncio.run(run())


if __name__ == "__main__":
    main()
