"""Render structured profiles into a self-contained, styled HTML report.

Mirrors `briefing.render_briefing` but emits a single .html file (inline CSS, no
external assets) that opens in any browser — a color-coded 2x2 SWOT grid, a
styled pricing table, and collapsible per-competitor profiles. Use the browser's
"Print to PDF" for a shareable document.
"""
from __future__ import annotations

from datetime import date
from html import escape
from typing import List, Optional

from .schemas import CompetitorProfile, SWOT

_CSS = """
:root {
  --bg: #f6f7f9; --card: #ffffff; --ink: #1c2330; --muted: #5b6573;
  --line: #e4e8ee; --accent: #2f6df6;
  --good: #1f9d57; --good-bg: #e9f7ef; --bad: #d6453d; --bad-bg: #fdecea;
  --opp: #2f6df6; --opp-bg: #eaf1fe; --thr: #c2790b; --thr-bg: #fbf1de;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 920px; margin: 0 auto; padding: 40px 24px 80px; }
header h1 { font-size: 1.9rem; margin: 0 0 6px; letter-spacing: -0.02em; }
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 28px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 22px 26px; margin-bottom: 22px; }
h2 { font-size: 1.15rem; margin: 0 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
h3 { font-size: 1.05rem; margin: 0 0 4px; }
ul { margin: 6px 0; padding-left: 20px; }
li { margin: 3px 0; }
a { color: var(--accent); text-decoration: none; word-break: break-all; }
a:hover { text-decoration: underline; }
.muted { color: var(--muted); font-style: italic; }
.takeaways li { margin: 6px 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.93rem; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: #f0f3f8; font-weight: 600; }
.swot { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.swot .quad { border-radius: 10px; padding: 14px 16px; }
.swot h4 { margin: 0 0 8px; font-size: 0.95rem; }
.swot ul { padding-left: 18px; }
.q-s { background: var(--good-bg); border: 1px solid var(--good); }
.q-s h4 { color: var(--good); }
.q-w { background: var(--bad-bg); border: 1px solid var(--bad); }
.q-w h4 { color: var(--bad); }
.q-o { background: var(--opp-bg); border: 1px solid var(--opp); }
.q-o h4 { color: var(--opp); }
.q-t { background: var(--thr-bg); border: 1px solid var(--thr); }
.q-t h4 { color: var(--thr); }
.profile { padding: 16px 0; border-bottom: 1px solid var(--line); }
.profile:last-child { border-bottom: 0; }
.profile .one-liner { color: var(--muted); font-style: italic; margin: 0 0 10px; }
.tag { display: inline-block; background: #eef1f6; color: var(--muted);
  border-radius: 999px; padding: 2px 10px; font-size: 0.8rem; margin: 2px 4px 2px 0; }
.own { display: inline-block; font-weight: 700; border-radius: 999px;
  padding: 3px 12px; font-size: 0.82rem; margin: 2px 0 8px; border: 1px solid; }
.own-pub { background: var(--good-bg); color: var(--good); border-color: var(--good); }
.own-priv { background: #eef1f6; color: #3a4250; border-color: #c7ccd6; }
.own-unk { background: var(--thr-bg); color: var(--thr); border-color: var(--thr); }
.loc-us { background: var(--opp-bg); color: var(--opp); border-color: var(--opp); }
.loc-intl { background: #efeafe; color: #534ab7; border-color: #7f77dd; }
.loc-unk { background: #eef1f6; color: #3a4250; border-color: #c7ccd6; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.label { font-weight: 600; font-size: 0.9rem; margin: 12px 0 4px; }
details { margin-top: 10px; }
summary { cursor: pointer; color: var(--muted); font-size: 0.88rem; }
footer { color: var(--muted); font-size: 0.82rem; text-align: center; margin-top: 30px; }
@media (max-width: 640px) { .swot, .cols { grid-template-columns: 1fr; } }
"""


def _li(items: List[str], empty: str = "None found.") -> str:
    items = [i for i in items if i and i.strip()]
    if not items:
        return f'<p class="muted">{escape(empty)}</p>'
    lis = "".join(f"<li>{escape(i)}</li>" for i in items)
    return f"<ul>{lis}</ul>"


def _quad(css: str, label: str, items: List[str]) -> str:
    items = [i for i in items if i and i.strip()]
    body = (
        "".join(f"<li>{escape(i)}</li>" for i in items)
        if items
        else '<li class="muted">None identified.</li>'
    )
    return f'<div class="quad {css}"><h4>{escape(label)}</h4><ul>{body}</ul></div>'


def _swot_html(target: str, swot: SWOT) -> str:
    return (
        f'<p class="muted">How {escape(target)} stands in this competitive field.</p>'
        '<div class="swot">'
        + _quad("q-s", "Strengths", swot.strengths)
        + _quad("q-w", "Weaknesses", swot.weaknesses)
        + _quad("q-o", "Opportunities", swot.opportunities)
        + _quad("q-t", "Threats", swot.threats)
        + "</div>"
    )


def _pricing_html(profiles: List[CompetitorProfile]) -> str:
    rows = []
    for p in profiles:
        if not p.pricing:
            rows.append(
                f'<tr><td>{escape(p.name)}</td><td>—</td>'
                f'<td class="muted">Not found</td><td></td></tr>'
            )
            continue
        for i, tier in enumerate(p.pricing):
            name_cell = escape(p.name) if i == 0 else ""
            rows.append(
                f"<tr><td>{name_cell}</td><td>{escape(tier.name)}</td>"
                f"<td>{escape(tier.price)}</td><td>{escape(tier.notes)}</td></tr>"
            )
    if not rows:
        return '<p class="muted">No pricing data found.</p>'
    return (
        "<table><thead><tr><th>Competitor</th><th>Plan</th><th>Price</th>"
        "<th>Notes</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _ownership_badge(p: CompetitorProfile) -> str:
    """Bold, color-coded public/private callout."""
    if p.is_public is True:
        ticker = f" ({escape(p.stock_ticker)})" if p.stock_ticker else ""
        return f'<span class="own own-pub">Publicly traded{ticker}</span>'
    if p.is_public is False:
        return '<span class="own own-priv">Privately held</span>'
    return '<span class="own own-unk">Ownership: not determined</span>'


def _location_badge(p: CompetitorProfile) -> str:
    """Bold, color-coded US / non-US callout with HQ country."""
    country = escape(p.headquarters_country.strip())
    if p.is_us_based is True:
        return f'<span class="own loc-us">US-based — {country or "United States"}</span>'
    if p.is_us_based is False:
        return f'<span class="own loc-intl">Non-US — {country or "country unknown"}</span>'
    if country:
        return f'<span class="own loc-unk">HQ: {country}</span>'
    return '<span class="own loc-unk">HQ: not determined</span>'


def _profile_html(p: CompetitorProfile) -> str:
    site = (
        f' — <a href="{escape(p.website)}">{escape(p.website)}</a>' if p.website else ""
    )
    parts = [f'<div class="profile"><h3>{escape(p.name)}{site}</h3>']
    parts.append(
        f'<div>{_ownership_badge(p)} {_location_badge(p)}</div>'
    )
    if p.one_liner:
        parts.append(f'<p class="one-liner">{escape(p.one_liner)}</p>')
    if p.positioning:
        parts.append(f"<p><strong>Positioning:</strong> {escape(p.positioning)}</p>")
    if p.target_segments:
        tags = "".join(f'<span class="tag">{escape(s)}</span>' for s in p.target_segments)
        parts.append(f'<p class="label">Target segments</p>{tags}')

    pricing = ""
    if p.pricing:
        rows = "".join(
            f"<li><strong>{escape(t.name)}:</strong> {escape(t.price)}"
            + (f" — {escape(t.notes)}" if t.notes else "")
            + "</li>"
            for t in p.pricing
        )
        pricing = f'<div><p class="label">Pricing</p><ul>{rows}</ul></div>'

    parts.append(
        '<div class="cols">'
        f'<div><p class="label">Key features</p>{_li(p.key_features)}</div>'
        f"{pricing}"
        f'<div><p class="label">Strengths</p>{_li(p.strengths)}</div>'
        f'<div><p class="label">Weaknesses / gaps</p>{_li(p.weaknesses)}</div>'
        "</div>"
        f'<p class="label">Recent news</p>{_li(p.recent_news)}'
    )
    if p.sources:
        srcs = "".join(
            f'<li><a href="{escape(s)}">{escape(s)}</a></li>' for s in p.sources
        )
        parts.append(f"<details><summary>Sources</summary><ul>{srcs}</ul></details>")
    parts.append("</div>")
    return "".join(parts)


def render_html(
    target: str,
    profiles: List[CompetitorProfile],
    executive_summary: str = "",
    key_takeaways: List[str] | None = None,
    swot: Optional[SWOT] = None,
) -> str:
    """Render the briefing as a self-contained HTML document (string)."""
    key_takeaways = key_takeaways or []
    names = ", ".join(p.name for p in profiles) or "—"

    body = [
        '<div class="wrap"><header>',
        f"<h1>Competitive Analysis — {escape(target)}</h1>",
        f'<div class="meta">Generated {date.today().isoformat()} · '
        f"Competitors analyzed: {escape(names)}</div></header>",
        "<section><h2>Executive Summary</h2>"
        f"<p>{escape(executive_summary) if executive_summary else ''}</p>"
        + ("" if executive_summary else '<p class="muted">Not generated.</p>')
        + "</section>",
        '<section><h2>Key Takeaways</h2>'
        f'<div class="takeaways">{_li(key_takeaways, empty="None.")}</div></section>',
    ]
    if swot is not None:
        body.append(
            f"<section><h2>SWOT — {escape(target)}</h2>{_swot_html(target, swot)}</section>"
        )
    body.append(
        f"<section><h2>Pricing at a Glance</h2>{_pricing_html(profiles)}</section>"
    )
    body.append(
        "<section><h2>Competitor Profiles</h2>"
        + "".join(_profile_html(p) for p in profiles)
        + "</section>"
    )
    body.append(
        "<footer>Produced by the Market Research Agent (LangGraph). "
        "Insights are model-extracted from public web sources — verify before acting.</footer>"
    )
    body.append("</div>")

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Competitive Analysis — {escape(target)}</title>"
        f"<style>{_CSS}</style></head><body>"
        + "".join(body)
        + "</body></html>\n"
    )
