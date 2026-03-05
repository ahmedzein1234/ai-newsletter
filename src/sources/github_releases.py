"""GitHub releases and trending repos (free with GITHUB_TOKEN)."""
from __future__ import annotations

import asyncio

import httpx

from ..config import settings

_REPOS_TO_WATCH = [
    "anthropics/claude-code",
    "anthropics/anthropic-sdk-python",
    "modelcontextprotocol/servers",
    "langchain-ai/langchain",
    "run-llama/llama_index",
]

_TRENDING_QUERY = "AI tools OR LLM OR claude created:>2025-01-01 stars:>50"


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    headers = {}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    headers["Accept"] = "application/vnd.github+json"

    articles: list[dict] = []

    async def _releases(repo: str) -> list[dict]:
        url = f"https://api.github.com/repos/{repo}/releases"
        try:
            resp = await client.get(url, headers=headers, params={"per_page": 3}, timeout=15)
            if resp.status_code != 200:
                return []
        except httpx.HTTPError:
            return []

        out = []
        for r in resp.json()[:3]:
            out.append({
                "id": f"gh-{repo}-{r['tag_name']}",
                "title": f"{repo} {r['tag_name']}: {r.get('name', '')}",
                "url": r.get("html_url", ""),
                "source": "GitHub",
                "points": 0,
                "published": r.get("published_at", ""),
                "summary": (r.get("body") or "")[:300],
            })
        return out

    async def _trending() -> list[dict]:
        url = "https://api.github.com/search/repositories"
        params = {"q": _TRENDING_QUERY, "sort": "updated", "per_page": 10}
        try:
            resp = await client.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                return []
        except httpx.HTTPError:
            return []

        out = []
        for repo in resp.json().get("items", [])[:10]:
            out.append({
                "id": f"gh-trending-{repo['full_name']}",
                "title": f"{repo['full_name']} ({repo.get('stargazers_count', 0)} stars)",
                "url": repo.get("html_url", ""),
                "source": "GitHub Trending",
                "points": repo.get("stargazers_count", 0),
                "published": repo.get("updated_at", ""),
                "summary": repo.get("description", "") or "",
            })
        return out

    tasks = [_releases(r) for r in _REPOS_TO_WATCH] + [_trending()]
    results = await asyncio.gather(*tasks)

    seen: set[str] = set()
    for batch in results:
        for a in batch:
            if a["id"] not in seen:
                seen.add(a["id"])
                articles.append(a)

    return articles[:30]
