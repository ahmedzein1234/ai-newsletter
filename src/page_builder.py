"""Build static HTML pages for Cloudflare Pages."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import markdown as md
from markupsafe import Markup
from jinja2 import Environment, FileSystemLoader

from .config import settings


_SECTION_TITLES = {
    "claude_news": "What's New in Claude",
    "claude_plugins": "Fresh MCPs, Plugins & Skills",
    "ai_tools": "AI Tools That Just Dropped",
    "ai_startups_uae": "Steal This Startup (UAE Edition)",
    "ai_realestate": "AI Meets Property",
    "world_news": "World News & Geopolitics",
    "monetization": "Turn This Into Money",
    "crypto": "Crypto Pulse: Sentiment & 24h Call",
    "gold_quant": "Gold & Quant Signals",
    "quick_links": "Quick Links Worth Your Click",
}

_SECTION_COLORS = {
    "claude_news": "#7c3aed",
    "claude_plugins": "#6366f1",
    "ai_tools": "#2563eb",
    "ai_startups_uae": "#059669",
    "ai_realestate": "#0891b2",
    "world_news": "#dc2626",
    "monetization": "#ea580c",
    "crypto": "#d97706",
    "gold_quant": "#b45309",
    "quick_links": "#64748b",
}

_SECTION_ORDER = [
    "claude_news", "claude_plugins", "ai_tools", "ai_startups_uae",
    "ai_realestate", "world_news", "monetization", "crypto", "gold_quant",
    "quick_links",
]


_DISPLAY_NAMES = {
    "BTCUSDT": ("BTC", "Bitcoin"),
    "ETHUSDT": ("ETH", "Ethereum"),
    "SOLUSDT": ("SOL", "Solana"),
    "XRPUSDT": ("XRP", "XRP"),
    "BNBUSDT": ("BNB", "BNB"),
    "ADAUSDT": ("ADA", "Cardano"),
    "DOGEUSDT": ("DOGE", "Dogecoin"),
    "AVAXUSDT": ("AVAX", "Avalanche"),
}

_DASHBOARD_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _md_to_html(text: str) -> Markup:
    """Convert markdown text to HTML, bypassing Jinja2 autoescape."""
    if not text:
        return Markup("")
    # Strip any ## headers the LLM may still produce — convert to bold paragraphs
    text = re.sub(r'^#{1,3}\s+(.+)$', r'**\1**', text, flags=re.MULTILINE)
    html = md.markdown(text, extensions=["tables", "sane_lists"])
    return Markup(html)


def _extract_crypto_dashboard(market_snapshot: dict | None) -> list[dict]:
    """Extract top crypto prices for the dashboard cards."""
    if not market_snapshot:
        return []
    prices = market_snapshot.get("prices", {})
    if not prices:
        return []
    dashboard = []
    for sym in _DASHBOARD_COINS:
        data = prices.get(sym)
        if not data:
            continue
        ticker, name = _DISPLAY_NAMES.get(sym, (sym[:3], sym.replace("USDT", "")))
        dashboard.append({
            "ticker": ticker,
            "name": name,
            "price": data["price"],
            "change": data["change"],
            "volume": data["volume"],
            "up": data["change"] >= 0,
        })
    return dashboard


def _env() -> Environment:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)

    def _importance_class(value):
        v = int(value) if value else 0
        if v >= 9:
            return "high"
        if v >= 7:
            return "medium"
        if v >= 5:
            return "low"
        return "none"

    env.filters["importance_class"] = _importance_class
    return env


def _extract_must_reads(articles: list[dict]) -> list[dict]:
    candidates = [a for a in articles if a.get("importance", 0) >= 7]
    candidates.sort(key=lambda x: x.get("importance", 0), reverse=True)
    return candidates[:3]


def _group_sections(articles: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for a in articles:
        sec = a.get("section", "quick_links")
        groups.setdefault(sec, []).append(a)

    out = []
    for key in _SECTION_ORDER:
        items = groups.get(key, [])
        if items:
            out.append({
                "key": key,
                "title": _SECTION_TITLES.get(key, key),
                "color": _SECTION_COLORS.get(key, "#64748b"),
                "entries": items,
            })
    return out


def _format_date(today: date) -> str:
    return today.strftime("%b %d, %Y").replace(" 0", " ")


def build_daily_page(
    articles: list[dict],
    today: date,
    analysis: str = "",
    monetization_ideas: str = "",
    uae_analysis: str = "",
    news_digest: str = "",
    world_analysis: str = "",
    cost_info: dict | None = None,
    total_read_time: int = 0,
    market_snapshot: dict | None = None,
) -> str:
    env = _env()
    tmpl = env.get_template("page.html")

    sections = _group_sections(articles)
    must_reads = _extract_must_reads(articles)
    date_formatted = _format_date(today)
    crypto_dashboard = _extract_crypto_dashboard(market_snapshot)
    fng = market_snapshot.get("fear_greed", {}) if market_snapshot else {}

    html = tmpl.render(
        date=today.isoformat(),
        date_formatted=date_formatted,
        sections=sections,
        must_reads=must_reads,
        analysis=_md_to_html(analysis),
        monetization_ideas=_md_to_html(monetization_ideas),
        uae_analysis=_md_to_html(uae_analysis),
        news_digest=_md_to_html(news_digest),
        world_analysis=_md_to_html(world_analysis),
        cost_info=cost_info,
        total_read_time=total_read_time,
        site_url=settings.site_url,
        crypto_dashboard=crypto_dashboard,
        fear_greed=fng,
    )

    out_dir = Path(settings.site_dir) / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def build_email(
    articles: list[dict],
    today: date,
    analysis: str = "",
    monetization_ideas: str = "",
    uae_analysis: str = "",
    news_digest: str = "",
    world_analysis: str = "",
    cost_info: dict | None = None,
    total_read_time: int = 0,
    market_snapshot: dict | None = None,
) -> str:
    env = _env()
    tmpl = env.get_template("email.html")

    sections = _group_sections(articles)
    must_reads = _extract_must_reads(articles)
    date_formatted = _format_date(today)
    page_url = f"{settings.site_url}/{today.isoformat()}/"
    crypto_dashboard = _extract_crypto_dashboard(market_snapshot)
    fng = market_snapshot.get("fear_greed", {}) if market_snapshot else {}

    return tmpl.render(
        date=today.isoformat(),
        date_formatted=date_formatted,
        sections=sections,
        must_reads=must_reads,
        page_url=page_url,
        analysis=_md_to_html(analysis),
        monetization_ideas=_md_to_html(monetization_ideas),
        uae_analysis=_md_to_html(uae_analysis),
        news_digest=_md_to_html(news_digest),
        world_analysis=_md_to_html(world_analysis),
        cost_info=cost_info,
        total_read_time=total_read_time,
        crypto_dashboard=crypto_dashboard,
        fear_greed=fng,
    )


def rebuild_archive_index() -> None:
    site = Path(settings.site_dir)
    editions = sorted(
        [d.name for d in site.iterdir() if d.is_dir() and d.name[:2] == "20"],
        reverse=True,
    )

    items_html = "\n".join(
        f'<li><a href="{e}/">{e}</a></li>' for e in editions
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zein's AI Newsletter Archive</title>
<link rel="stylesheet" href="style.css">
</head><body>
<div class="container">
<h1>Zein's AI Newsletter Archive</h1>
<p>Daily curated AI + market intelligence.</p>
<ul class="archive-list">{items_html}</ul>
</div>
</body></html>"""

    (site / "index.html").write_text(html, encoding="utf-8")
