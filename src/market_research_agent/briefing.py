"""Render structured profiles into a formatted Markdown briefing."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from .schemas import CompetitorProfile, SWOT


def _bullets(items: List[str], empty: str = "_None found._") -> str:
    items = [i for i in items if i and i.strip()]
    if not items:
        return empty
    return "\n".join(f"- {i}" for i in items)


def _swot_cell(label: str, items: List[str]) -> str:
    """One quadrant of the 2x2 grid, bullets joined with <br> for table cells."""
    items = [i for i in items if i and i.strip()]
    body = "<br>".join(f"• {i}" for i in items) if items else "_None identified._"
    return f"**{label}**<br>{body}"


def _swot_grid(target: str, swot: SWOT) -> str:
    """Classic 2x2 SWOT table (Helpful/Harmful × Internal/External)."""
    return "\n".join([
        f"_How {target} stands in this competitive field._",
        "",
        "|  | Helpful | Harmful |",
        "|---|---|---|",
        f"| **Internal** | {_swot_cell('Strengths', swot.strengths)} "
        f"| {_swot_cell('Weaknesses', swot.weaknesses)} |",
        f"| **External** | {_swot_cell('Opportunities', swot.opportunities)} "
        f"| {_swot_cell('Threats', swot.threats)} |",
    ])


def _pricing_table(profiles: List[CompetitorProfile]) -> str:
    rows = ["| Competitor | Plan | Price | Notes |", "|---|---|---|---|"]
    any_row = False
    for p in profiles:
        if not p.pricing:
            rows.append(f"| {p.name} | — | _Not found_ | |")
            continue
        for i, tier in enumerate(p.pricing):
            name_cell = p.name if i == 0 else ""
            rows.append(
                f"| {name_cell} | {tier.name} | {tier.price} | {tier.notes} |"
            )
            any_row = True
    return "\n".join(rows) if any_row or profiles else "_No pricing data found._"


def _ownership_label(p: CompetitorProfile) -> str:
    """Bold public/private callout for a competitor."""
    if p.is_public is True:
        ticker = f" ({p.stock_ticker})" if p.stock_ticker else ""
        return f"**🌐 Publicly traded{ticker}**"
    if p.is_public is False:
        return "**🔒 Privately held**"
    return "**❔ Ownership: not determined**"


def _location_label(p: CompetitorProfile) -> str:
    """Bold US / non-US callout with the HQ country."""
    country = p.headquarters_country.strip()
    if p.is_us_based is True:
        return f"**🇺🇸 US-based — {country or 'United States'}**"
    if p.is_us_based is False:
        return f"**🌍 Non-US — {country or 'country unknown'}**"
    if country:
        return f"**📍 HQ: {country}**"
    return "**📍 HQ: not determined**"


def _profile_section(p: CompetitorProfile) -> str:
    website = f" — [{p.website}]({p.website})" if p.website else ""
    parts = [f"### {p.name}{website}", ""]
    parts += [f"{_ownership_label(p)} · {_location_label(p)}", ""]
    if p.one_liner:
        parts += [f"*{p.one_liner}*", ""]
    if p.positioning:
        parts += [f"**Positioning:** {p.positioning}", ""]
    if p.target_segments:
        parts += [f"**Target segments:** {', '.join(p.target_segments)}", ""]
    parts += ["**Key features:**", _bullets(p.key_features), ""]
    if p.pricing:
        parts += ["**Pricing:**"]
        for t in p.pricing:
            note = f" — {t.notes}" if t.notes else ""
            parts.append(f"- **{t.name}:** {t.price}{note}")
        parts += [""]
    parts += ["**Strengths:**", _bullets(p.strengths), ""]
    parts += ["**Weaknesses / gaps:**", _bullets(p.weaknesses), ""]
    parts += ["**Recent news:**", _bullets(p.recent_news), ""]
    if p.sources:
        srcs = "\n".join(f"- {s}" for s in p.sources)
        parts += ["<details><summary>Sources</summary>", "", srcs, "", "</details>", ""]
    return "\n".join(parts)


def render_briefing(
    target: str,
    profiles: List[CompetitorProfile],
    executive_summary: str = "",
    key_takeaways: List[str] | None = None,
    swot: Optional[SWOT] = None,
) -> str:
    key_takeaways = key_takeaways or []
    names = ", ".join(p.name for p in profiles) or "—"
    doc: List[str] = [
        f"# Competitive Analysis Briefing — {target}",
        "",
        f"_Generated {date.today().isoformat()} · Competitors analyzed: {names}_",
        "",
        "## Executive Summary",
        "",
        executive_summary or "_Not generated._",
        "",
        "## Key Takeaways",
        "",
        _bullets(key_takeaways, empty="_None._"),
        "",
    ]
    if swot is not None:
        doc += [
            f"## SWOT — {target}",
            "",
            _swot_grid(target, swot),
            "",
        ]
    doc += [
        "## Pricing at a Glance",
        "",
        _pricing_table(profiles),
        "",
        "## Competitor Profiles",
        "",
    ]
    for p in profiles:
        doc.append(_profile_section(p))
    doc += [
        "---",
        "_Produced by the Market Research Agent (LangGraph). "
        "Insights are model-extracted from public web sources — verify before acting._",
    ]
    return "\n".join(doc)
