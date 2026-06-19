"""Shared graph state."""
from __future__ import annotations

from typing import List, TypedDict


class GraphState(TypedDict, total=False):
    target: str                 # company/product being analyzed
    competitors: List[str]      # discovered competitor names
    profiles: List[dict]        # CompetitorProfile dumps
    executive_summary: str
    key_takeaways: List[str]
    swot: dict                  # target-focused SWOT (or None)
    briefing: str               # final rendered markdown
    metrics: dict               # cost / latency / reliability summary
