"""High-level entrypoint tying config, tools and graph together."""
from __future__ import annotations

import uuid
from typing import Callable, List, Optional

from langchain_core.tools import BaseTool
from langgraph.types import Command

from .config import Settings
from .graph import build_graph
from .guardrails import validate_target
from .tools import build_tools

# Called when the graph pauses for human review. Receives the interrupt payload
# ({"target": ..., "proposed_competitors": [...]}) and returns the approved list.
HumanReviewFn = Callable[[dict], List[str]]


def run_analysis(
    target: str,
    settings: Settings | None = None,
    *,
    extra_tools: List[BaseTool] | None = None,
    progress: Callable[[str], None] = lambda _: None,
    human_review: Optional[HumanReviewFn] = None,
) -> dict:
    """Run the full competitor analysis for `target`.

    Returns the final graph state, including a `briefing` markdown string and a
    `metrics` dict. If `settings.human_review` is on and a `human_review`
    callback is supplied, the graph pauses after competitor discovery and the
    callback decides the final competitor list.
    """
    settings = settings or Settings.from_env()
    settings.require_llm()
    target = validate_target(target)
    tools = build_tools(settings, extra=extra_tools, progress=progress)
    app = build_graph(settings, tools, progress=progress)

    use_review = settings.human_review and human_review is not None
    config = {"configurable": {"thread_id": uuid.uuid4().hex}} if use_review else None

    result = app.invoke({"target": target}, config)

    # Drive any human-in-the-loop interrupts to completion.
    while use_review and "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        approved = human_review(payload)
        result = app.invoke(Command(resume=approved), config)

    return result
