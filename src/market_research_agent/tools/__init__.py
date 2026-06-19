"""Tool assembly."""
from __future__ import annotations

from typing import Callable, List

from langchain_core.tools import BaseTool

from ..config import Settings
from .mcp import load_bundled_tools
from .web_fetch import make_fetch_tool
from .web_search import make_search_tool


def build_tools(
    settings: Settings,
    extra: List[BaseTool] | None = None,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> List[BaseTool]:
    """Core research tools, the bundled MCP tools, plus any extra ones supplied.

    The bundled Hacker News MCP tool loads by default (toggle with
    `settings.hn_tool` / `MRA_HN`); it degrades gracefully if MCP deps are absent.
    """
    tools: List[BaseTool] = [make_search_tool(settings), make_fetch_tool(settings)]
    if settings.hn_tool:
        tools.extend(load_bundled_tools(progress=progress))
    if extra:
        tools.extend(extra)
    return tools


__all__ = ["build_tools", "make_search_tool", "make_fetch_tool"]
