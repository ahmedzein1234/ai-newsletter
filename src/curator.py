"""LLM curation via OpenRouter (Kimi K2.5 primary)."""
from __future__ import annotations

import json
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)

_MODELS = [
    "moonshotai/kimi-k2.5",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct:free",
]

_CURATION_PROMPT = """\
You are an AI newsletter curator for a developer who works with:
- Claude Code (skills, plugins, MCP servers)
- AI video/image generators (Gemini, FLUX, Runway, Kling)
- Crypto trading bots (Binance spot, halal-filtered altcoins)
- Medical textbook production (matplotlib diagrams, ReportLab PDFs)
- Children's book creation (Arabic/English, PIL)
- Web design and Cloudflare deployment

Categorize each article into EXACTLY ONE section:
1. "claude" - Claude Code, Anthropic, MCP servers, skills/plugins
2. "tools" - AI models, video/image generators, new APIs
3. "monetization" - Monetizing AI skills, freelancing, SaaS
4. "projects" - Relevant to trading, books, medical, web design
5. "links" - Interesting but doesn't fit above

Rate relevance 1-10. Drop anything below 4.
Return JSON array of objects with: id, section, relevance, one_line_summary (max 15 words).
No markdown fences. Just the JSON array."""

_ANALYSIS_PROMPT = """\
You are a sharp crypto and commodities market analyst writing for a developer \
who runs automated spot trading bots on Binance (halal-filtered altcoins only — \
no lending tokens, no derivatives, no stablecoins).

Given today's market data and news headlines, write TWO short analysis sections:

## 1. Crypto Market: Sentiment & 24h Outlook
- Current BTC/ETH/SOL prices and 24h changes (use the data provided)
- Fear & Greed Index reading and what it signals
- Key news that could move prices in the next 24 hours
- Concrete 24h expectation: bullish/bearish/neutral with brief reasoning
- Any altcoin-specific signals worth watching
- 150-200 words max

## 2. Gold & Quant Trading
- Current gold price and trend
- Key macro factors affecting gold (Fed, inflation, geopolitics)
- Notable quant/algo trading developments or strategies in the news
- 24h gold outlook: up/down/flat with reasoning
- 100-150 words max

Write in a direct, no-fluff style. Use specific numbers. No disclaimers. \
Format as markdown with ## headers. Be opinionated — give a clear directional call."""


async def curate(articles: list[dict]) -> list[dict]:
    if not articles:
        return []
    if not settings.openrouter_api_key:
        return _keyword_fallback(articles)

    # Separate pre-tagged articles (crypto/gold) from general articles
    general = [a for a in articles if "section" not in a]
    pretagged = [a for a in articles if "section" in a]

    # Curate general articles via LLM
    curated_general = []
    if general:
        capped = general[:60]
        titles = [{"id": a["id"], "title": a["title"], "source": a["source"]} for a in capped]
        prompt = f"Curate these {len(titles)} articles:\n{json.dumps(titles)}"

        for model in _MODELS:
            try:
                result = await _call_llm(model, _CURATION_PROMPT, prompt)
                if result and isinstance(result, list):
                    curated_general = _merge(capped, result)
                    break
            except Exception as e:
                log.warning("LLM %s curation failed: %s", model, e)
        else:
            curated_general = _keyword_fallback(general)

    return curated_general + pretagged


async def generate_analysis(articles: list[dict]) -> str:
    """Generate crypto + gold analysis using market data from fetched articles."""
    crypto_data = [a for a in articles if a.get("section") == "crypto"]
    gold_data = [a for a in articles if a.get("section") == "gold_quant"]

    context_parts = []
    for a in crypto_data:
        meta = a.get("meta", {})
        if meta:
            context_parts.append(f"- {a['title']} | meta: {json.dumps(meta)}")
        else:
            context_parts.append(f"- {a['title']}")
    for a in gold_data:
        meta = a.get("meta", {})
        if meta:
            context_parts.append(f"- {a['title']} | meta: {json.dumps(meta)}")
        else:
            context_parts.append(f"- {a['title']}")

    if not context_parts:
        return ""

    prompt = f"Today's market data and headlines:\n" + "\n".join(context_parts)

    for model in _MODELS:
        try:
            text = await _call_llm_text(model, _ANALYSIS_PROMPT, prompt)
            if text and len(text) > 100:
                log.info("Analysis generated via %s (%d chars)", model, len(text))
                return text
        except Exception as e:
            log.warning("LLM %s analysis failed: %s", model, e)

    log.warning("All LLMs failed for analysis, returning empty")
    return ""


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

        return resp.json()["choices"][0]["message"]["content"].strip()


def _merge(articles: list[dict], curated: list[dict]) -> list[dict]:
    cmap = {c["id"]: c for c in curated if c.get("relevance", 0) >= 4}
    out = []
    for a in articles:
        if a["id"] in cmap:
            c = cmap[a["id"]]
            a["section"] = c.get("section", "links")
            a["relevance"] = c.get("relevance", 5)
            a["one_line"] = c.get("one_line_summary", a["title"][:80])
            out.append(a)
    out.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return out


_SECTION_KEYWORDS = {
    "claude": ["claude", "anthropic", "mcp", "claude code"],
    "tools": ["ai tool", "generator", "model", "api", "llm", "gpt", "gemini", "flux", "runway", "dall-e"],
    "monetization": ["monetiz", "freelanc", "saas", "revenue", "income", "earn"],
    "projects": ["trading", "crypto", "binance", "medical", "textbook", "book", "cloudflare", "web design"],
}


def _keyword_fallback(articles: list[dict]) -> list[dict]:
    out = []
    for a in articles:
        text = f"{a['title']} {a.get('summary', '')}".lower()
        section = "links"
        for sec, keywords in _SECTION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                section = sec
                break
        a["section"] = section
        a["relevance"] = 5
        a["one_line"] = a["title"][:80]
        out.append(a)
    return out
