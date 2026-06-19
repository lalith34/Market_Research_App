"""Hacker News MCP server — a free, no-key data source for the research agent.

Exposes Hacker News search via the public Algolia HN Search API
(https://hn.algolia.com/api). It surfaces recent discussion, sentiment, and
launch/news signals about a company or product — a strong complement to generic
web search when building the "recent news" part of a competitive briefing.

Run standalone (stdio transport):

    python -m market_research_agent.mcp_servers.hn_server

Or wire it into the agent via mcp_servers.json (see mcp_servers.example.json):

    {
      "hacker_news": {
        "command": "python",
        "args": ["-m", "market_research_agent.mcp_servers.hn_server"],
        "transport": "stdio"
      }
    }

Requires the optional MCP SDK: ``pip install "mcp[cli]"``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The Hacker News MCP server requires the MCP SDK: pip install 'mcp[cli]'"
    ) from exc

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_HEADERS = {"User-Agent": "market-research-agent/0.1 (+https://hn.algolia.com)"}

mcp = FastMCP("hacker_news")


def _format_hit(hit: dict) -> str:
    title = hit.get("title") or hit.get("story_title") or "(untitled)"
    points = hit.get("points") or 0
    comments = hit.get("num_comments") or 0
    obj_id = hit.get("objectID", "")
    discussion = f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else ""
    article = hit.get("url") or discussion

    created = hit.get("created_at_i")
    when = ""
    if created:
        when = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")

    lines = [f"- {title}"]
    meta = [p for p in (when, f"{points} points", f"{comments} comments") if p]
    if meta:
        lines.append(f"  {' · '.join(meta)}")
    if article:
        lines.append(f"  article: {article}")
    if discussion and discussion != article:
        lines.append(f"  discussion: {discussion}")
    return "\n".join(lines)


@mcp.tool()
def hn_search(query: str, limit: int = 5, by_date: bool = False) -> str:
    """Search Hacker News stories for a company, product, or topic.

    Use to gauge recent news, launches, and developer/market sentiment about a
    competitor. Returns the top stories with points, comment counts, dates, and
    links to both the article and the HN discussion thread.

    Args:
        query: What to search for, e.g. a company or product name ("Notion").
        limit: Max stories to return (1-20, default 5).
        by_date: If true, sort by most recent instead of by relevance/points.
    """
    query = (query or "").strip()
    if not query:
        return "hn_search error: empty query."

    limit = max(1, min(int(limit), 20))
    endpoint = f"{_SEARCH_URL}_by_date" if by_date else _SEARCH_URL
    params = {"query": query, "tags": "story", "hitsPerPage": limit}

    try:
        with httpx.Client(timeout=15.0, headers=_HEADERS) as client:
            resp = client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # network / parse errors -> readable tool result
        return f"hn_search error for {query!r}: {exc}"

    hits = data.get("hits") or []
    if not hits:
        return f"No Hacker News stories found for {query!r}."

    header = f"Top {len(hits)} Hacker News stories for {query!r}:"
    return header + "\n" + "\n".join(_format_hit(h) for h in hits)


def main() -> None:
    """Console entry point: run the server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
