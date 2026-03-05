"""LLM curation via OpenRouter (free Gemini 2.0 Flash)."""
from __future__ import annotations

import json
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)

_MODELS = [
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct:free",
]

_SYSTEM_PROMPT = """\
You are an AI newsletter curator for a developer who works with:
- Claude Code (skills, plugins, MCP servers)
- AI video/image generators (Gemini, FLUX, Runway, Kling)
- Crypto trading bots (Binance spot)
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


async def curate(articles: list[dict]) -> list[dict]:
    if not articles:
        return []
    if not settings.openrouter_api_key:
        return _keyword_fallback(articles)

    # Cap at 60 articles to stay within token limits
    capped = articles[:60]
    titles = [{"id": a["id"], "title": a["title"], "source": a["source"]} for a in capped]

    prompt = f"Curate these {len(titles)} articles:\n{json.dumps(titles)}"

    for model in _MODELS:
        try:
            result = await _call_llm(model, prompt)
            if result:
                return _merge(capped, result)
        except Exception as e:
            log.warning("LLM %s failed: %s", model, e)

    log.info("All LLMs failed, using keyword fallback")
    return _keyword_fallback(articles)


async def _call_llm(model: str, prompt: str) -> list[dict] | None:
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
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 8000,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("OpenRouter %d: %s", resp.status_code, resp.text[:200])
            return None

        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = text.removeprefix("```json").removesuffix("```").strip()
        return json.loads(text)


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
