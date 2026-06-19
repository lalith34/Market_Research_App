"""LangGraph workflow: discover -> research -> synthesize.

    target ──> [discover] ──> [research] ──> [synthesize] ──> briefing
                  │
                  └─(optional human-in-the-loop: approve/edit competitors)

`research` runs a bounded, loop-guarded tool-calling loop (web_search +
fetch_page) for each competitor, then extracts a structured CompetitorProfile.
`synthesize` drafts the executive layer and optionally refines it with a
Reflection pass (Draft -> Critique -> Revise).

The design folds in several agent-engineering patterns explicitly:
  * Failure-mode hardening (loop / duplicate-call / wrong-tool guards).
  * Human-in-the-loop review checkpoint.
  * Reflection design pattern.
  * Cost / latency / reliability metrics (see metrics.py).
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable, List

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .config import Settings
from .extract import structured_invoke
from .llm import make_llm
from .metrics import RunMetrics
from .prompts import (
    DISCOVERY_GUIDANCE,
    DISCOVERY_SYSTEM,
    EXTRACTION_SYSTEM,
    REFLECTION_CRITIQUE_SYSTEM,
    REFLECTION_REVISE_SYSTEM,
    RESEARCH_SYSTEM,
    SWOT_SYSTEM,
    SYNTHESIS_SYSTEM,
)
from .schemas import SWOT, CompetitorList, CompetitorProfile
from .state import GraphState

ProgressFn = Callable[[str], None]


class _Synthesis(BaseModel):
    executive_summary: str = Field(default="")
    key_takeaways: List[str] = Field(default_factory=list)


def _call_key(call: dict) -> str:
    """Stable identity for a tool call (name + canonicalized args)."""
    return call["name"] + ":" + json.dumps(call.get("args", {}), sort_keys=True)


def _dedupe(names: List[str]) -> List[str]:
    """Drop case-insensitive duplicates, preserving first-seen order."""
    out: List[str] = []
    seen: set[str] = set()
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def _pinned_competitors(settings: Settings) -> List[str]:
    """Caller-provided competitor list (cleaned + deduped), or [] if none."""
    return _dedupe([str(n).strip() for n in settings.competitors if str(n).strip()])


def _seed_queries(target: str, mode: str) -> List[str]:
    """Discovery search seeds, phrased for a brand, a category, or both (auto)."""
    brand = [f"top competitors of {target}", f"best {target} alternatives"]
    category = [f"best {target} brands", f"top {target} companies", f"{target} market leaders"]
    if mode == "brand":
        return brand
    if mode == "category":
        return category
    # auto: blend brand- and category-style phrasings so either kind of target
    # surfaces good evidence without an extra classification call.
    return [brand[0], category[0], category[2]]


def _fetched_urls(messages: List[BaseMessage]) -> List[str]:
    """URLs the agent successfully fetched during the research loop, in order."""
    urls: List[str] = []
    for m in messages:
        for call in getattr(m, "tool_calls", None) or []:
            if call["name"] == "fetch_page":
                url = call["args"].get("url", "")
                if url and url not in urls:
                    urls.append(url)
    return urls


def _format_tools(tools: List[BaseTool]) -> str:
    """Bullet list of available tools (name + one-line description) for the prompt.

    Lets the research prompt advertise *all* bound tools — including MCP ones —
    so the model actually reaches for them, instead of only the hard-coded two.
    """
    lines = []
    for t in tools:
        first = (t.description or "").strip().splitlines()
        summary = first[0].strip() if first else ""
        if len(summary) > 160:
            summary = summary[:157] + "..."
        lines.append(f"- {t.name}: {summary}")
    return "\n".join(lines)


def _tool_text(result) -> str:
    """Normalize a tool result to plain text.

    Built-in tools return a string; MCP-adapter tools return a list of content
    blocks like [{"type": "text", "text": "..."}]. Flatten the latter to text.
    """
    if isinstance(result, list):
        parts = []
        for block in result:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(result)


def _invoke_tool(tool: BaseTool, args: dict) -> str:
    """Invoke a tool, supporting both sync tools and async-only ones (MCP).

    MCP-adapter tools raise NotImplementedError on sync `.invoke`; fall back to
    running their coroutine. The graph runs synchronously (no active event loop),
    so a fresh loop via asyncio.run is safe here.
    """
    try:
        result = tool.invoke(args)
    except NotImplementedError:
        result = asyncio.run(tool.ainvoke(args))
    return _tool_text(result)


def _run_tool_loop(
    llm_with_tools,
    tool_map: dict[str, BaseTool],
    messages: List[BaseMessage],
    max_steps: int,
    progress: ProgressFn,
    metrics: RunMetrics,
) -> List[BaseMessage]:
    """Drive the model through tool calls until it stops or hits max_steps.

    Hardened against the Session-1 failure modes:
      * **Loops / wasted tokens** — identical (tool, args) calls are served from
        a cache instead of re-executed, and an all-duplicate round breaks early.
      * **Hallucinated tool calls** — unknown tool names are reported, not run.
      * **Bad tool calls** — tool exceptions are caught and surfaced to the model.
    """
    seen: dict[str, str] = {}
    for _ in range(max_steps):
        ai: AIMessage = llm_with_tools.invoke(messages)
        metrics.record_usage(ai)
        messages.append(ai)
        if not getattr(ai, "tool_calls", None):
            break

        made_progress = False
        for call in ai.tool_calls:
            metrics.record_tool(call["name"])
            preview = call["args"].get("query") or call["args"].get("url") or ""
            key = _call_key(call)

            if key in seen:
                metrics.duplicate_tool_calls += 1
                progress(f"      · {call['name']}({preview}) ↻ cached (skip repeat)")
                messages.append(
                    ToolMessage(
                        content=(
                            "[loop guard] You already ran this exact call. "
                            "Reusing the earlier result:\n" + seen[key]
                        ),
                        tool_call_id=call["id"],
                    )
                )
                continue

            tool = tool_map.get(call["name"])
            if tool is None:
                metrics.unknown_tool_calls += 1
                available = ", ".join(tool_map) or "(none)"
                result = f"Unknown tool '{call['name']}'. Available tools: {available}."
                progress(f"      · !unknown tool {call['name']}")
            else:
                try:
                    result = _invoke_tool(tool, call["args"])
                except Exception as exc:
                    metrics.tool_errors += 1
                    result = f"Tool error: {exc}"
                progress(f"      · {call['name']}({preview})")
                made_progress = True

            seen[key] = result
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

        # Whole round was duplicates/unknowns → the model is looping; stop.
        if not made_progress:
            progress("      · loop guard: no new evidence this round, stopping")
            break
    return messages


def _reflect(
    llm,
    target: str,
    compact_profiles: str,
    draft: _Synthesis,
    rounds: int,
    progress: ProgressFn,
    metrics: RunMetrics,
) -> _Synthesis:
    """Reflection pattern: critique the draft, then revise it. Best-effort."""
    current = draft
    for i in range(max(0, rounds)):
        try:
            critique_msgs = [
                SystemMessage(content=REFLECTION_CRITIQUE_SYSTEM.format(target=target)),
                HumanMessage(
                    content=(
                        f"Competitor profiles:\n{compact_profiles}\n\n"
                        f"Draft executive_summary:\n{current.executive_summary}\n\n"
                        f"Draft key_takeaways:\n- " + "\n- ".join(current.key_takeaways)
                    )
                ),
            ]
            critique = llm.invoke(critique_msgs)
            metrics.record_usage(critique)
            critique_text = str(getattr(critique, "content", "")).strip()
            if not critique_text or "no changes needed" in critique_text.lower():
                progress("      · reflection: draft accepted, no changes")
                break

            progress("      · reflection: revising per critique")
            revise_msgs = [
                SystemMessage(content=REFLECTION_REVISE_SYSTEM.format(target=target)),
                HumanMessage(
                    content=(
                        f"Competitor profiles:\n{compact_profiles}\n\n"
                        f"Current executive_summary:\n{current.executive_summary}\n\n"
                        f"Current key_takeaways:\n- " + "\n- ".join(current.key_takeaways)
                        + f"\n\nEditor critique:\n{critique_text}"
                    )
                ),
            ]
            current = structured_invoke(llm, _Synthesis, revise_msgs, metrics=metrics)
        except Exception as exc:
            progress(f"      ! reflection round {i + 1} failed: {exc}")
            break
    return current


def build_graph(
    settings: Settings,
    tools: List[BaseTool],
    progress: ProgressFn = lambda _: None,
    metrics: RunMetrics | None = None,
):
    """Compile and return the LangGraph app."""
    metrics = metrics or RunMetrics()
    llm = make_llm(settings)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    # ---- node: discover competitors -------------------------------------
    def discover(state: GraphState) -> GraphState:
        target = state["target"]

        # Explicit list pinned by the caller → skip discovery entirely. Honors
        # exactly what was provided (deduped), not the max_competitors cap.
        pinned = _pinned_competitors(settings)
        if pinned:
            names = pinned
            progress(f"[discover] using provided competitors -> {', '.join(names)}")
        else:
            mode = settings.discovery_mode
            noun = "brands/players in" if mode == "category" else "competitors of"
            progress(f"[discover] finding {noun} {target} (mode={mode})…")
            search = tool_map.get("web_search")
            evidence = ""
            if search is not None:
                for q in _seed_queries(target, mode):
                    metrics.record_tool("web_search")
                    evidence += search.invoke({"query": q, "max_results": 5}) + "\n"
            messages = [
                SystemMessage(content=DISCOVERY_SYSTEM.format(
                    guidance=DISCOVERY_GUIDANCE[mode],
                    max_competitors=settings.max_competitors,
                )),
                HumanMessage(content=f"Target: {target}\n\nSearch results:\n{evidence}"),
            ]
            result = structured_invoke(llm, CompetitorList, messages, metrics=metrics)
            names = [n.strip() for n in result.competitors if n.strip()][: settings.max_competitors]
            progress(f"[discover] -> {', '.join(names) or 'none'}")

        # Human-in-the-loop checkpoint: let a human approve/edit before the
        # expensive research stage. `interrupt` pauses the graph; the resumed
        # value (a list of names) replaces the proposal.
        if settings.human_review:
            decision = interrupt({"target": target, "proposed_competitors": names})
            if isinstance(decision, list):
                names = [str(n).strip() for n in decision if str(n).strip()]
                progress(f"[discover] human-approved -> {', '.join(names) or 'none'}")
        return {"competitors": names}

    # ---- node: research each competitor ---------------------------------
    def research(state: GraphState) -> GraphState:
        tools_desc = _format_tools(tools)
        profiles: List[dict] = []
        for name in state.get("competitors", []):
            progress(f"[research] {name}…")
            messages: List[BaseMessage] = [
                SystemMessage(content=RESEARCH_SYSTEM.format(competitor=name, tools=tools_desc)),
                HumanMessage(content=f"Research {name}. Begin."),
            ]
            messages = _run_tool_loop(
                llm_with_tools, tool_map, messages, settings.max_research_steps, progress, metrics
            )
            # Gather the full evidence trail (the model's reasoning + every fetched
            # page), not just the last message — otherwise a run that hits the step
            # budget mid-fetch would extract from a single raw page.
            notes = "\n\n".join(
                str(m.content)
                for m in messages
                if isinstance(m, (AIMessage, ToolMessage)) and m.content
            )
            # Track pages the agent actually fetched, so sources survive even when
            # the model omits them from its prose summary.
            fetched_urls = _fetched_urls(messages)
            extract_msgs = [
                SystemMessage(content=EXTRACTION_SYSTEM),
                HumanMessage(content=f"Competitor: {name}\n\nResearch notes:\n{notes}"),
            ]
            try:
                profile = structured_invoke(llm, CompetitorProfile, extract_msgs, metrics=metrics)
            except Exception as exc:
                progress(f"      ! extraction failed for {name}: {exc}")
                profile = CompetitorProfile(name=name)
            # Always use the canonical name we set out to research. The extracted
            # `name` is redundant and open models sometimes fill it with a
            # description instead of the actual name.
            profile.name = name
            # Merge fetched URLs as a fallback, de-duped, preserving model-cited order.
            seen = set(profile.sources)
            for url in fetched_urls:
                if url not in seen:
                    profile.sources.append(url)
                    seen.add(url)
            profiles.append(profile.model_dump())
        return {"profiles": profiles}

    # ---- node: synthesize briefing --------------------------------------
    def synthesize(state: GraphState) -> GraphState:
        target = state["target"]
        progress("[synthesize] writing executive summary…")
        profiles = [CompetitorProfile.model_validate(p) for p in state.get("profiles", [])]
        compact = "\n\n".join(
            f"{p.name}: {p.one_liner}\n  positioning: {p.positioning}\n"
            f"  features: {', '.join(p.key_features[:6])}\n"
            f"  pricing: {', '.join(f'{t.name} {t.price}' for t in p.pricing)}\n"
            f"  strengths: {', '.join(p.strengths[:4])}\n"
            f"  weaknesses: {', '.join(p.weaknesses[:4])}\n"
            f"  news: {', '.join(p.recent_news[:3])}"
            for p in profiles
        )
        messages = [
            SystemMessage(content=SYNTHESIS_SYSTEM.format(target=target)),
            HumanMessage(content=f"Competitor profiles:\n{compact}"),
        ]
        try:
            syn = structured_invoke(llm, _Synthesis, messages, metrics=metrics)
        except Exception as exc:
            progress(f"      ! synthesis failed: {exc}")
            syn = _Synthesis()

        # Reflection pattern: Draft -> Critique -> Revise.
        if settings.reflection and (syn.executive_summary or syn.key_takeaways):
            syn = _reflect(
                llm, target, compact, syn, settings.max_reflection_rounds, progress, metrics
            )

        # Target-focused SWOT, grounded in the profiles + (reflected) summary.
        swot: SWOT | None = None
        if settings.swot and profiles:
            progress("[synthesize] building SWOT…")
            swot_msgs = [
                SystemMessage(content=SWOT_SYSTEM.format(target=target)),
                HumanMessage(
                    content=(
                        f"Executive summary:\n{syn.executive_summary}\n\n"
                        f"Competitor profiles:\n{compact}"
                    )
                ),
            ]
            try:
                swot = structured_invoke(llm, SWOT, swot_msgs, metrics=metrics)
            except Exception as exc:
                progress(f"      ! SWOT generation failed: {exc}")
                swot = None

        from .briefing import render_briefing

        briefing = render_briefing(
            target, profiles, syn.executive_summary, syn.key_takeaways, swot
        )
        return {
            "executive_summary": syn.executive_summary,
            "key_takeaways": syn.key_takeaways,
            "swot": swot.model_dump() if swot else None,
            "briefing": briefing,
            "metrics": metrics.finalize().to_dict(),
        }

    g = StateGraph(GraphState)
    g.add_node("discover", discover)
    g.add_node("research", research)
    g.add_node("synthesize", synthesize)
    g.set_entry_point("discover")
    g.add_edge("discover", "research")
    g.add_edge("research", "synthesize")
    g.add_edge("synthesize", END)
    # A checkpointer is required for interrupt()/resume; only pay for it when
    # human review is enabled.
    checkpointer = MemorySaver() if settings.human_review else None
    return g.compile(checkpointer=checkpointer)
