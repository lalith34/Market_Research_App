"""Command-line interface.

    market-research "Notion" --competitors 3 --output samples/notion.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings
from .guardrails import GuardrailError, validate_target
from .pipeline import run_analysis


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="market-research",
        description="Autonomous competitor-analysis research agent.",
    )
    p.add_argument("target", help="Company or product to analyze (e.g. 'Notion').")
    p.add_argument("-n", "--competitors", type=int, help="Max competitors to research (count).")
    p.add_argument(
        "--competitors-list",
        help="Comma-separated competitors to research verbatim, skipping discovery "
        "(e.g. \"Coda, Linear, Obsidian\").",
    )
    p.add_argument("-m", "--model", help="Override model id (Nebius).")
    p.add_argument("--search", choices=["auto", "ddg", "tavily"], help="Search backend.")
    p.add_argument(
        "--mode",
        choices=["auto", "brand", "category"],
        help="Treat the target as a specific brand/product, a market category, or auto-detect.",
    )
    p.add_argument(
        "-o",
        "--output",
        help="Write the briefing to this file. Format is inferred from the "
        "extension (.md / .html) unless --format is given.",
    )
    p.add_argument(
        "--format",
        choices=["auto", "md", "markdown", "html"],
        default="auto",
        help="Output format. 'auto' infers from --output's extension (default md).",
    )
    p.add_argument(
        "--review",
        action="store_true",
        help="Human-in-the-loop: approve/edit the competitor list before researching.",
    )
    p.add_argument(
        "--no-reflect",
        action="store_true",
        help="Disable the reflection (Draft→Critique→Revise) pass on the briefing.",
    )
    p.add_argument(
        "--no-swot",
        action="store_true",
        help="Omit the target-focused SWOT analysis section.",
    )
    p.add_argument(
        "--mcp-config",
        help="Path to an MCP servers JSON file (see mcp_servers.example.json). Their "
        "tools are loaded and made available to the agent alongside the built-ins.",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress progress logs.")
    return p


def _prompt_review(payload: dict) -> list[str]:
    """Interactive stdin review of the discovered competitor list."""
    proposed = payload.get("proposed_competitors", [])
    target = payload.get("target", "the target")
    print(f"\n── Human review ── proposed competitors for {target}:", file=sys.stderr)
    for i, name in enumerate(proposed, 1):
        print(f"  {i}. {name}", file=sys.stderr)
    print(
        "Press Enter to accept, or type a comma-separated list to replace them:",
        file=sys.stderr,
        end=" ",
    )
    try:
        reply = input().strip()
    except EOFError:
        reply = ""
    if not reply:
        return list(proposed)
    return [n.strip() for n in reply.split(",") if n.strip()]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    settings = Settings.from_env()
    if args.competitors:
        settings.max_competitors = args.competitors
    if args.model:
        settings.model = args.model
    if args.search:
        settings.search = args.search
    if args.mode:
        settings.mode = args.mode
    if args.competitors_list:
        settings.competitors = [c.strip() for c in args.competitors_list.split(",") if c.strip()]
    if args.review:
        settings.human_review = True
    if args.no_reflect:
        settings.reflection = False
    if args.no_swot:
        settings.swot = False

    try:
        settings.require_llm()
        validate_target(args.target)
    except (RuntimeError, GuardrailError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def progress(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    extra_tools = None
    if args.mcp_config:
        try:
            extra_tools = _load_mcp_config(args.mcp_config)
        except Exception as exc:
            print(f"error: failed to load MCP config {args.mcp_config!r}: {exc}", file=sys.stderr)
            return 2
        names = ", ".join(t.name for t in extra_tools) or "(none)"
        print(f"Loaded MCP tools from {args.mcp_config}: {names}", file=sys.stderr)

    print(
        f"Analyzing '{args.target}' · mode={settings.discovery_mode} · "
        f"model={settings.model} · search={settings.search_backend}",
        file=sys.stderr,
    )
    state = run_analysis(
        args.target,
        settings,
        extra_tools=extra_tools,
        progress=progress,
        human_review=_prompt_review if settings.human_review else None,
    )
    fmt = _resolve_format(args.format, args.output)
    content = _render(state, args.target, fmt)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        print(f"\nBriefing ({fmt}) written to {out}", file=sys.stderr)
    else:
        print("\n" + content)

    metrics = state.get("metrics")
    if metrics:
        print("\n" + _format_metrics(metrics), file=sys.stderr)
    return 0


def _load_mcp_config(path: str):
    """Load MCP tools from a JSON config file (sync wrapper around the async loader)."""
    import asyncio

    from .tools.mcp import load_mcp_tools

    if not Path(path).is_file():
        raise FileNotFoundError(path)
    return asyncio.run(load_mcp_tools(path))


def _resolve_format(fmt: str, output: str | None) -> str:
    """Resolve the output format: explicit flag wins, else infer from extension."""
    if fmt in {"md", "markdown"}:
        return "markdown"
    if fmt == "html":
        return "html"
    # auto: infer from the output file's extension, defaulting to markdown.
    if output and Path(output).suffix.lower() in {".html", ".htm"}:
        return "html"
    return "markdown"


def _render(state: dict, target: str, fmt: str) -> str:
    """Produce the briefing in the requested format from the final state."""
    if fmt == "markdown":
        return state.get("briefing", "")

    # HTML is rendered from the structured data, not the markdown string.
    from .html_report import render_html
    from .schemas import SWOT, CompetitorProfile

    profiles = [CompetitorProfile.model_validate(p) for p in state.get("profiles", [])]
    swot_raw = state.get("swot")
    swot = SWOT.model_validate(swot_raw) if swot_raw else None
    return render_html(
        target,
        profiles,
        state.get("executive_summary", ""),
        state.get("key_takeaways", []),
        swot,
    )


def _format_metrics(m: dict) -> str:
    """Render the metrics dict (from state) into the CLI footer line."""
    toks = (
        f"{m.get('total_tokens', 0):,} tokens "
        f"({m.get('input_tokens', 0):,} in / {m.get('output_tokens', 0):,} out)"
    )
    line = (
        f"⏱  {m.get('elapsed_s', 0)}s · {m.get('llm_calls', 0)} LLM calls · {toks} · "
        f"{m.get('tool_calls', 0)} tool calls"
    )
    flags = []
    if m.get("duplicate_tool_calls"):
        flags.append(f"{m['duplicate_tool_calls']} duplicate")
    if m.get("unknown_tool_calls"):
        flags.append(f"{m['unknown_tool_calls']} unknown-tool")
    if m.get("tool_errors"):
        flags.append(f"{m['tool_errors']} tool-error")
    if flags:
        line += "\n   ⚠ reliability: " + ", ".join(flags)
    return line


if __name__ == "__main__":
    raise SystemExit(main())
