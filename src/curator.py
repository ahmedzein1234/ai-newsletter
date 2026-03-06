"""LLM curation via OpenRouter (GPT 5.2 for analysis, Gemini for curation)."""
from __future__ import annotations

import json
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)

# Curation model (fast, cheap — just JSON classification)
_CURATION_MODELS = [
    "google/gemini-2.0-flash-001",
    "moonshotai/kimi-k2.5",
    "meta-llama/llama-3.3-70b-instruct:free",
]

# Analysis models (quality writing — GPT 5.2 primary)
_ANALYSIS_MODELS = [
    "openai/gpt-5.2",
    "google/gemini-2.0-flash-001",
    "moonshotai/kimi-k2.5",
]

_cost_counter = {"llm_calls": 0, "est_tokens": 0}

_CURATION_PROMPT = """\
You are an AI newsletter curator for a developer who works with:
- Claude Code (skills, plugins, MCP servers)
- AI video/image generators (Gemini, FLUX, Runway, Kling)
- Crypto trading bots (Binance spot, halal-filtered altcoins)
- Medical textbook production (matplotlib diagrams, ReportLab PDFs)
- Children's book creation (Arabic/English, PIL)
- Web design and Cloudflare deployment
- UAE real estate and proptech
- AI startup ecosystem (especially UAE/MENA)

Categorize each article into EXACTLY ONE section:
1. "claude_news" — Claude Code, Anthropic announcements, Claude model updates
2. "claude_plugins" — MCP servers, plugins, skills, Claude extensions, tool integrations
3. "ai_tools" — AI models, video/image generators, new APIs, developer tools
4. "ai_startups_uae" — AI startups, funding rounds, UAE tech ecosystem
5. "ai_realestate" — AI in real estate, proptech, property management AI
6. "monetization" — Monetizing AI skills, freelancing, SaaS ideas
7. "world_news" — Major international events, geopolitics, breaking world news
8. "quick_links" — Interesting but doesn't fit above (catch-all)

Note: "crypto" and "gold_quant" articles are pre-tagged and will NOT appear here.

IMPORTANT — DEDUPLICATION:
Many articles cover the same story from different sources. If multiple articles \
are about the same topic/event, ONLY include the BEST one (highest quality source, \
most detail). Drop the duplicates entirely (do not include them in your output). \
For example, if 3 articles cover "GPT-5 release", pick the one from the best \
source and drop the other two.

Rate importance 0-10. Drop anything below 4.
Return a JSON array of objects with these fields:
- id (string): the article id
- section (string): one of the section keys above
- importance (int 0-10): how relevant/important for this audience
- editorial_title (string): catchy rewrite of the title, max 12 words
- summary (string): 2-3 sentence summary explaining what happened and why it \
matters for this audience. Be specific — include names, numbers, and key details. \
40-60 words.
- word_count_estimate (int): estimated word count of the full article

No markdown fences. Just the raw JSON array."""

_ANALYSIS_PROMPT = """\
You are a sharp crypto and commodities market analyst writing for a developer \
who runs automated spot trading bots on Binance (halal-filtered altcoins only — \
no lending tokens, no derivatives, no stablecoins).

Given today's structured market data (Binance prices, BTC Guru scores, Pulse Trader \
bot status, Fear & Greed), write TWO short analysis paragraphs:

**Crypto Market: Sentiment & 24h Outlook** (200-250 words)
Cover BTC/ETH/SOL prices and 24h changes, BTC Guru ensemble score and regime, \
Fear & Greed reading, Pulse Trader bot status (open positions, P&L), key news \
that could move prices, concrete 24h call (bullish/bearish/neutral), and any \
altcoin signals worth watching.

**Gold & Quant Trading** (100-150 words)
Cover gold price and trend, macro factors (Fed, inflation, geopolitics), \
notable quant/algo developments, and 24h gold outlook.

Write in flowing paragraphs. Use **bold** for emphasis and key numbers. \
Do NOT use markdown headers (##, ###). Do NOT use bullet lists. \
Structure with paragraph breaks and bold labels, not headers. \
Be direct, no-fluff. Use specific numbers. No disclaimers. Be opinionated."""

_MONETIZATION_PROMPT = """\
You are a sharp business strategist advising a developer who builds AI tools, \
trading bots, and content-generation pipelines. Given today's AI/tech news, \
suggest 3-5 concrete monetization ideas inspired by these articles.

For each idea, write a short paragraph with the idea name in bold, followed by \
a 2-3 sentence description, effort level (Low/Medium/High), revenue estimate \
($/mo range), and why today's news makes it timely.

Write in flowing paragraphs. Use **bold** for emphasis and key terms. \
Do NOT use markdown headers (##, ###). Do NOT use bullet lists. \
Structure with paragraph breaks and bold labels, not headers. \
Be specific and actionable. No generic advice. Target $500-$10,000/mo ideas \
that a solo developer can build in 1-4 weeks."""

_UAE_STARTUP_PROMPT = """\
You are a tech-savvy startup analyst focused on the UAE and MENA region. \
Given today's AI/tech news, identify 2-3 AI startups or products mentioned \
that could be replicated or adapted for the UAE market.

For each opportunity, write a short paragraph with the startup/product name in \
bold, covering what they do, why it would work in UAE/MENA, concrete first steps \
for a solo developer, and existing competition in the region.

Write in flowing paragraphs. Use **bold** for emphasis and key terms. \
Do NOT use markdown headers (##, ###). Do NOT use bullet lists. \
Structure with paragraph breaks and bold labels, not headers. \
Be specific about UAE market dynamics. Consider Arabic language needs, \
Islamic finance requirements, and local regulations."""

_NEWS_DIGEST_PROMPT = """\
You are a sharp tech journalist writing a daily briefing for an AI developer. \
Synthesize today's AI and tech news into a cohesive 150-200 word narrative.

Open with the biggest story of the day (1-2 sentences), connect 2-3 related \
themes, note what's genuinely new vs yesterday (use previous edition context), \
and close with one thing to watch.

Write in flowing paragraphs. Use **bold** for emphasis and key terms. \
Do NOT use markdown headers (##, ###). Do NOT use bullet lists. \
Use specific company names, numbers, and product names. No fluff."""

_WORLD_ANALYSIS_PROMPT = """\
You are a geopolitics analyst writing for a tech developer and crypto trader. \
Analyze the major world events from the last 24 hours and their impact on \
technology markets and crypto.

Write 150-200 words covering the top 2-3 world events, their impact on \
tech/crypto markets, anything affecting UAE/MENA directly, and one \
geopolitical trend to watch this week.

Write in flowing paragraphs. Use **bold** for emphasis and key terms. \
Do NOT use markdown headers (##, ###). Do NOT use bullet lists. \
Be direct and opinionated. Use specific names, dates, and numbers. No disclaimers."""


async def curate(articles: list[dict]) -> list[dict]:
    if not articles:
        return []
    if not settings.openrouter_api_key:
        return _keyword_fallback(articles)

    general = [a for a in articles if "section" not in a]
    pretagged = [a for a in articles if "section" in a]

    curated_general = []
    if general:
        capped = general[:60]
        titles = [
            {"id": a["id"], "title": a["title"], "source": a["source"]}
            for a in capped
        ]
        prompt = f"Curate these {len(titles)} articles:\n{json.dumps(titles)}"

        for model in _CURATION_MODELS:
            try:
                result = await _call_llm(model, _CURATION_PROMPT, prompt)
                if result and isinstance(result, list):
                    curated_general = _merge(capped, result)
                    break
            except Exception as e:
                log.warning("LLM %s curation failed: %s", model, e)
        else:
            curated_general = _keyword_fallback(general)

    for a in pretagged:
        a.setdefault("importance", 7)
        a.setdefault("relevance", a.get("importance", 7))
        a.setdefault("editorial_title", a["title"][:80])
        a.setdefault("one_line", a.get("one_line", a["title"][:80]))
        a.setdefault("read_time", 2)

    return curated_general + pretagged


async def generate_analysis(
    articles: list[dict],
    market_snapshot: dict | None = None,
    prev_context: str = "",
) -> str:
    """Generate crypto + gold analysis using structured market snapshot."""
    context_parts = []

    # Add previous edition context
    if prev_context:
        context_parts.append(prev_context)
        context_parts.append("---")

    # Build structured market data from snapshot (always fresh, never deduped)
    if market_snapshot:
        context_parts.append("TODAY'S LIVE MARKET DATA:")

        prices = market_snapshot.get("prices", {})
        if prices:
            context_parts.append("\nBinance Spot Prices (24h):")
            for sym, data in prices.items():
                name = sym.replace("USDT", "")
                arrow = "+" if data["change"] >= 0 else ""
                context_parts.append(
                    f"  {name}: ${data['price']:,.2f} ({arrow}{data['change']:.1f}%) "
                    f"Vol: ${data['volume']/1e6:,.0f}M"
                )

        guru = market_snapshot.get("btc_guru", {})
        if guru:
            context_parts.append(f"\nBTC Guru Analysis:")
            context_parts.append(f"  Ensemble Score: {guru.get('ensemble', 'N/A')}")
            context_parts.append(f"  Regime: {guru.get('regime', 'N/A')}")
            context_parts.append(f"  RSI 1h/4h: {guru.get('rsi_1h', 'N/A')}/{guru.get('rsi_4h', 'N/A')}")
            context_parts.append(f"  MACD Hist: {guru.get('macd_hist', 'N/A')}")
            context_parts.append(f"  Trends 1h/4h/1d: {guru.get('trend_1h')}/{guru.get('trend_4h')}/{guru.get('trend_1d')}")
            context_parts.append(f"  Prediction: {guru.get('direction')} ({guru.get('confidence', 0):.0f}% conf)")
            context_parts.append(f"  Target: ${guru.get('target', 0):,.0f}")
            context_parts.append(f"  Funding Rate: {guru.get('funding_rate', 'N/A')}")
            context_parts.append(f"  Long/Short Ratio: {guru.get('long_short_ratio', 'N/A')}")
            if guru.get("gold_price"):
                context_parts.append(f"  Gold: ${guru['gold_price']:,.2f} ({guru.get('gold_change_pct', 0):+.1f}%)")
            if guru.get("vix"):
                context_parts.append(f"  VIX: {guru['vix']:.1f} | S&P 500: {guru.get('sp500_change', 0):+.1f}%")

        fng = market_snapshot.get("fear_greed", {})
        if fng:
            context_parts.append(f"\nFear & Greed Index: {fng.get('value', '?')}/100 — {fng.get('label', '?')}")

        pt = market_snapshot.get("pulse_trader", {})
        if pt:
            context_parts.append(f"\nPulse Trader Bot Status:")
            context_parts.append(f"  Open positions: {pt.get('open_count', 0)}")
            if pt.get("open_positions"):
                for p in pt["open_positions"][:5]:
                    context_parts.append(f"    {p['symbol']} ({p['strategy']}) @ ${p['entry']:,.4f}")
            context_parts.append(f"  24h closed: {pt.get('closed_24h', 0)} ({pt.get('wins', 0)}W/{pt.get('losses', 0)}L)")
            context_parts.append(f"  24h P&L: ${pt.get('pnl_usdt', 0):+.2f} USDT ({pt.get('daily_pnl_pct', 0):+.2f}%)")

    # Also include article titles as supplementary context
    crypto_data = [a for a in articles if a.get("section") == "crypto"]
    gold_data = [a for a in articles if a.get("section") == "gold_quant"]
    if crypto_data or gold_data:
        context_parts.append("\nRelated Headlines:")
        for a in crypto_data + gold_data:
            context_parts.append(f"  - {a['title']}")

    if len(context_parts) <= 2:
        return ""

    prompt = "\n".join(context_parts)

    for model in _ANALYSIS_MODELS:
        try:
            text = await _call_llm_text(model, _ANALYSIS_PROMPT, prompt)
            if text and len(text) > 100:
                log.info("Analysis generated via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s analysis failed: %s", model, e)

    log.warning("All LLMs failed for analysis, returning empty")
    return ""


async def generate_monetization_ideas(articles: list[dict]) -> str:
    """Generate monetization ideas inspired by today's curated articles."""
    relevant = [
        a for a in articles
        if a.get("section") in (
            "ai_tools", "claude_news", "claude_plugins",
            "ai_startups_uae", "monetization",
        )
    ]
    if not relevant:
        relevant = articles[:15]

    summaries = []
    for a in relevant[:20]:
        title = a.get("editorial_title", a.get("title", ""))
        line = a.get("one_line", "")
        summaries.append(f"- {title}: {line}" if line else f"- {title}")

    prompt = "Today's AI/tech news:\n" + "\n".join(summaries)

    for model in _ANALYSIS_MODELS:
        try:
            text = await _call_llm_text(model, _MONETIZATION_PROMPT, prompt)
            if text and len(text) > 100:
                log.info("Monetization ideas via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s monetization failed: %s", model, e)

    log.warning("All LLMs failed for monetization ideas, returning empty")
    return ""


async def generate_uae_startup_analysis(articles: list[dict]) -> str:
    """Identify AI startups/products that could be replicated in the UAE market."""
    relevant = [
        a for a in articles
        if a.get("section") in (
            "ai_startups_uae", "ai_tools", "ai_realestate",
            "monetization", "claude_news",
        )
    ]
    if not relevant:
        relevant = articles[:15]

    summaries = []
    for a in relevant[:20]:
        title = a.get("editorial_title", a.get("title", ""))
        line = a.get("one_line", "")
        summaries.append(f"- {title}: {line}" if line else f"- {title}")

    prompt = "Today's AI/tech news:\n" + "\n".join(summaries)

    for model in _ANALYSIS_MODELS:
        try:
            text = await _call_llm_text(model, _UAE_STARTUP_PROMPT, prompt)
            if text and len(text) > 100:
                log.info("UAE startup analysis via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s UAE startup analysis failed: %s", model, e)

    log.warning("All LLMs failed for UAE startup analysis, returning empty")
    return ""


async def generate_news_digest(articles: list[dict], prev_context: str = "") -> str:
    """Synthesize today's AI/tech news into a cohesive narrative."""
    relevant = [
        a for a in articles
        if a.get("section") in (
            "ai_tools", "claude_news", "claude_plugins",
            "ai_startups_uae", "monetization",
        )
    ]
    if not relevant:
        relevant = articles[:20]

    parts = []
    if prev_context:
        parts.append(prev_context)
        parts.append("---")

    parts.append("## Today's AI/Tech Headlines:")
    for a in relevant[:25]:
        title = a.get("editorial_title", a.get("title", ""))
        line = a.get("one_line", "")
        parts.append(f"- {title}: {line}" if line else f"- {title}")

    prompt = "\n".join(parts)

    for model in _ANALYSIS_MODELS:
        try:
            text = await _call_llm_text(model, _NEWS_DIGEST_PROMPT, prompt)
            if text and len(text) > 80:
                log.info("News digest via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s news digest failed: %s", model, e)

    log.warning("All LLMs failed for news digest, returning empty")
    return ""


async def generate_world_analysis(articles: list[dict]) -> str:
    """Analyze major world events and their impact on tech/markets."""
    relevant = [
        a for a in articles
        if a.get("section") == "world_news"
    ]
    # Also include general world-ish articles
    if len(relevant) < 5:
        for a in articles:
            title = (a.get("title", "") + " " + a.get("summary", "")).lower()
            if any(kw in title for kw in [
                "war", "sanction", "geopolit", "election", "summit", "trade war",
                "middle east", "nato", "un ", "united nations", "conflict",
                "oil price", "opec", "central bank", "fed ", "interest rate",
            ]):
                if a not in relevant:
                    relevant.append(a)

    if not relevant:
        return ""

    summaries = []
    for a in relevant[:20]:
        title = a.get("editorial_title", a.get("title", ""))
        summaries.append(f"- {title}")

    prompt = "Today's world news headlines:\n" + "\n".join(summaries)

    for model in _ANALYSIS_MODELS:
        try:
            text = await _call_llm_text(model, _WORLD_ANALYSIS_PROMPT, prompt)
            if text and len(text) > 80:
                log.info("World analysis via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s world analysis failed: %s", model, e)

    log.warning("All LLMs failed for world analysis, returning empty")
    return ""


def estimate_cost() -> dict:
    calls = _cost_counter["llm_calls"]
    tokens = _cost_counter["est_tokens"]
    cost = tokens * 0.000003  # rough GPT 5.2 rate
    return {"llm_calls": calls, "est_tokens": tokens, "est_cost_usd": round(cost, 4)}


async def _call_llm(model: str, system: str, prompt: str) -> list[dict] | None:
    text = await _call_llm_text(model, system, prompt)
    if not text:
        return None
    text = text.removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)


async def _call_llm_text(model: str, system: str, prompt: str) -> str | None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 8000,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            log.warning("OpenRouter %d: %s", resp.status_code, resp.text[:200])
            return None

        content = resp.json()["choices"][0]["message"]["content"].strip()
        est_tokens = len(system + prompt + content) // 4
        _cost_counter["llm_calls"] += 1
        _cost_counter["est_tokens"] += est_tokens
        return content


def _merge(articles: list[dict], curated: list[dict]) -> list[dict]:
    cmap = {c["id"]: c for c in curated if c.get("importance", 0) >= 4}
    out = []
    for a in articles:
        if a["id"] in cmap:
            c = cmap[a["id"]]
            a["section"] = c.get("section", "quick_links")
            a["importance"] = c.get("importance", 5)
            a["relevance"] = a["importance"]
            a["editorial_title"] = c.get("editorial_title", a["title"][:80])
            # Use new "summary" field (2-3 sentences), fall back to old "one_line_summary"
            a["one_line"] = c.get("summary", c.get("one_line_summary", a["title"][:80]))
            wc = c.get("word_count_estimate")
            a["read_time"] = max(1, wc // 200) if wc else 2
            out.append(a)
    out.sort(key=lambda x: x.get("importance", 0), reverse=True)
    return out


_SECTION_KEYWORDS = {
    "claude_news": ["claude", "anthropic", "claude code", "claude model"],
    "claude_plugins": ["mcp", "plugin", "skill", "extension", "tool integration"],
    "ai_tools": [
        "ai tool", "generator", "model", "api", "llm", "gpt", "gemini",
        "flux", "runway", "dall-e", "midjourney", "stable diffusion",
    ],
    "ai_startups_uae": [
        "startup", "funding", "uae", "dubai", "abu dhabi", "mena",
        "series a", "series b", "seed round",
    ],
    "ai_realestate": [
        "real estate", "proptech", "property", "realestate",
        "housing", "rental", "mortgage",
    ],
    "monetization": [
        "monetiz", "freelanc", "saas", "revenue", "income", "earn",
        "side project", "passive income",
    ],
    "world_news": [
        "war", "geopolit", "election", "sanction", "nato", "united nations",
        "summit", "conflict", "middle east", "trade war", "diplomacy",
    ],
}


def _keyword_fallback(articles: list[dict]) -> list[dict]:
    out = []
    for a in articles:
        text = f"{a['title']} {a.get('summary', '')}".lower()
        section = "quick_links"
        for sec, keywords in _SECTION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                section = sec
                break
        a["section"] = section
        a["importance"] = 5
        a["relevance"] = 5
        a["editorial_title"] = a["title"][:80]
        a["one_line"] = a["title"][:80]
        a["read_time"] = 2
        out.append(a)
    return out
