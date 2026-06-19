"""Optional: load custom MCP tool servers so engineers can add data sources.

This is intentionally lazy — `langchain-mcp-adapters` is an optional dependency.
Define servers in a JSON file and they become normal LangChain tools the agent
can call alongside web_search / fetch_page.

Example mcp_servers.json:
{
  "crunchbase": {
    "command": "npx",
    "args": ["-y", "@some/crunchbase-mcp"],
    "transport": "stdio"
  },
  "internal_docs": {
    "url": "http://localhost:8000/mcp",
    "transport": "streamable_http"
  }
}
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import List

from langchain_core.tools import BaseTool

# The Hacker News server bundled with this package (see mcp_servers/hn_server.py),
# launched over stdio with the *current* interpreter so it shares the venv.
BUNDLED_HN_SERVER = {
    "hacker_news": {
        "command": sys.executable,
        "args": ["-m", "market_research_agent.mcp_servers.hn_server"],
        "transport": "stdio",
    }
}


async def load_mcp_tools(config: str | Path | dict) -> List[BaseTool]:
    """Return LangChain tools exposed by the configured MCP servers.

    `config` may be a path to a JSON file or an already-parsed config dict.
    Raises a helpful error if the optional dependency is missing.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "MCP support requires `pip install langchain-mcp-adapters`."
        ) from exc

    if not isinstance(config, dict):
        config = json.loads(Path(config).read_text())
    client = MultiServerMCPClient(config)
    return await client.get_tools()


def load_bundled_tools(progress=lambda _: None) -> List[BaseTool]:
    """Synchronously load the bundled MCP tools (Hacker News).

    Degrades gracefully: if the optional MCP deps are missing or the server
    fails to launch, returns [] and notes it via `progress` rather than raising,
    so the core agent keeps working without MCP installed.
    """
    try:
        return asyncio.run(load_mcp_tools(BUNDLED_HN_SERVER))
    except RuntimeError as exc:
        msg = str(exc)
        if "MCP support requires" in msg:
            progress(
                "[mcp] Hacker News tool is enabled but MCP deps are missing; "
                "skipping. Install with: pip install langchain-mcp-adapters mcp"
            )
        elif "asyncio.run() cannot be called" in msg or "running event loop" in msg:
            # Called from within a running loop; let an async caller use
            # load_mcp_tools(BUNDLED_HN_SERVER) directly instead.
            progress("[mcp] Skipping bundled tools: already inside an event loop.")
        else:
            progress(f"[mcp] Could not load bundled Hacker News tool: {exc}")
        return []
    except Exception as exc:  # pragma: no cover - defensive
        progress(f"[mcp] Could not load bundled Hacker News tool: {exc}")
        return []
