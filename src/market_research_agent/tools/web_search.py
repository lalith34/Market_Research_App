"""Web search tool. DuckDuckGo by default (no key); Tavily if configured."""
from __future__ import annotations

from typing import List

from langchain_core.tools import StructuredTool
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings


def _ddg_search(query: str, max_results: int) -> List[dict]:
    from ddgs import DDGS

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8))
    def _go() -> List[dict]:
        with DDGS() as ddg:
            return list(ddg.text(query, max_results=max_results))

    try:
        rows = _go()
    except Exception as exc:  # rate limits / transient network
        return [{"title": "search_error", "href": "", "body": f"DuckDuckGo error: {exc}"}]
    return [
        {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
        for r in rows
    ]


def _tavily_search(query: str, max_results: int, api_key: str) -> List[dict]:
    from tavily import TavilyClient

    try:
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results)
    except Exception as exc:
        return [{"title": "search_error", "href": "", "body": f"Tavily error: {exc}"}]
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")}
        for r in resp.get("results", [])
    ]


def _format(rows: List[dict]) -> str:
    if not rows:
        return "No results."
    out = []
    for i, r in enumerate(rows, 1):
        out.append(f"[{i}] {r['title']}\n    {r['href']}\n    {r['body'][:400]}")
    return "\n".join(out)


def make_search_tool(settings: Settings) -> StructuredTool:
    backend = settings.search_backend

    def web_search(query: str, max_results: int = 5) -> str:
        """Search the web and return ranked results (title, url, snippet).

        Use for finding pricing pages, feature lists, comparisons and recent news.
        """
        max_results = max(1, min(int(max_results), 8))
        if backend == "tavily" and settings.tavily_api_key:
            rows = _tavily_search(query, max_results, settings.tavily_api_key)
        else:
            rows = _ddg_search(query, max_results)
        return _format(rows)

    return StructuredTool.from_function(
        func=web_search,
        name="web_search",
        description=(
            "Search the web for a query and return ranked results with title, URL and "
            "snippet. Use to discover pricing pages, feature lists, comparisons, and news."
        ),
    )
