"""SEC EDGAR MCP server — free, no-key financial-data source.

Looks a company up in the SEC's public registry and returns whether it's an SEC
registrant (i.e. publicly traded in the US), its ticker(s)/exchange(s), industry
(SIC), and most recent filings (10-K, 10-Q, 8-K, ...). This directly enriches the
agent's public/private callout: a hit here is strong evidence a competitor is
public; a miss is a useful signal it may be private or non-US.

Data: SEC's public JSON APIs (https://www.sec.gov/os/accessing-edgar-data).
No API key — the SEC only requires a descriptive User-Agent.

Run standalone:
    python -m market_research_agent.mcp_servers.edgar_server
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The EDGAR MCP server requires the MCP SDK: pip install mcp"
    ) from exc

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
# The SEC requires a User-Agent identifying the caller; no key is needed.
_HEADERS = {"User-Agent": "market-research-agent (contact: research@example.com)"}

mcp = FastMCP("sec_edgar")

_tickers_cache: Optional[List[dict]] = None


def _load_tickers(client: httpx.Client) -> List[dict]:
    """Fetch and cache the SEC ticker→CIK directory (a flat dict of records)."""
    global _tickers_cache
    if _tickers_cache is None:
        resp = client.get(_TICKERS_URL)
        resp.raise_for_status()
        data = resp.json()
        _tickers_cache = list(data.values())
    return _tickers_cache


# Generic corporate words ignored when comparing names, so "e.l.f. Cosmetics"
# can still match the registrant "e.l.f. Beauty, Inc." on the distinctive token.
_CORP_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "company", "co", "llc", "ltd",
    "limited", "plc", "holdings", "holding", "group", "the", "sa", "ag", "nv", "lp",
}


def _norm_tokens(s: str) -> List[str]:
    """Lowercase, drop intra-word dots/apostrophes (e.l.f. -> elf), split, drop stopwords."""
    s = s.lower().replace(".", "").replace("'", "")
    return [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _CORP_STOPWORDS]


def _match_company(records: List[dict], query: str) -> List[Tuple[str, str, str]]:
    """Return (cik10, ticker, title) matches, best first.

    Tiers: exact ticker, then full-name substring, then a distinctive first-token
    match (so "e.l.f. Cosmetics" finds "e.l.f. Beauty, Inc."). Pure / unit-testable.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    q_tokens = _norm_tokens(query)
    q_first = q_tokens[0] if q_tokens else ""
    ticker_hits, name_hits, token_hits = [], [], []
    for rec in records:
        ticker = str(rec.get("ticker", ""))
        title = str(rec.get("title", ""))
        cik10 = str(rec.get("cik_str", "")).zfill(10)
        if ticker.lower() == q:
            ticker_hits.append((cik10, ticker, title))
        elif q in title.lower():
            name_hits.append((cik10, ticker, title))
        elif len(q_first) >= 3:
            t_tokens = _norm_tokens(title)
            # Distinctive first token must be the title's first token too.
            if t_tokens and t_tokens[0] == q_first:
                token_hits.append((cik10, ticker, title))
    # Exact ticker / substring always win.
    if ticker_hits or name_hits:
        return ticker_hits + name_hits
    # Loose first-token tier only when UNAMBIGUOUS — a single candidate. Multiple
    # "Body …" companies for "The Body Shop" stay unmatched rather than guessing.
    return token_hits if len(token_hits) == 1 else []


@mcp.tool()
def edgar_lookup(company: str, max_filings: int = 5) -> str:
    """Look a company up in SEC EDGAR (US public-company registry).

    Use to confirm whether a competitor is publicly traded in the US and to pull
    its ticker, exchange, industry, and most recent SEC filings. A "not found"
    result is itself a signal the company is likely private or non-US.

    Args:
        company: Company name or ticker, e.g. "e.l.f. Beauty" or "ELF".
        max_filings: How many recent filings to list (1-15, default 5).
    """
    company = (company or "").strip()
    if not company:
        return "edgar_lookup error: empty company."
    max_filings = max(1, min(int(max_filings), 15))

    try:
        with httpx.Client(timeout=20.0, headers=_HEADERS) as client:
            records = _load_tickers(client)
            matches = _match_company(records, company)
            if not matches:
                return (
                    f"No exact match in the SEC EDGAR ticker registry for {company!r}. "
                    "It may be private, a subsidiary/brand of another registrant, or "
                    "non-US. Treat this as a hint, not proof — confirm via web search."
                )
            cik10, ticker, title = matches[0]
            resp = client.get(_SUBMISSIONS_URL.format(cik10=cik10))
            resp.raise_for_status()
            sub = resp.json()
    except Exception as exc:  # network/parse -> readable tool result
        return f"edgar_lookup error for {company!r}: {exc}"

    tickers = ", ".join(sub.get("tickers", []) or [ticker]) or "—"
    exchanges = ", ".join(sub.get("exchanges", []) or []) or "—"
    sic = sub.get("sicDescription", "") or "—"
    name = sub.get("name", title)

    lines = [
        f"SEC EDGAR — {name} (PUBLIC / SEC registrant)",
        f"  CIK: {cik10} · Ticker(s): {tickers} · Exchange(s): {exchanges}",
        f"  Industry (SIC): {sic}",
        "  Recent filings:",
    ]
    recent = (sub.get("filings", {}) or {}).get("recent", {}) or {}
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    cik_int = int(cik10)
    shown = 0
    for i in range(len(forms)):
        if shown >= max_filings:
            break
        accn = accns[i].replace("-", "") if i < len(accns) else ""
        doc = docs[i] if i < len(docs) else ""
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn}/{doc}"
            if accn and doc
            else ""
        )
        date = dates[i] if i < len(dates) else "?"
        lines.append(f"    - {forms[i]} ({date}){f' {url}' if url else ''}")
        shown += 1
    if shown == 0:
        lines.append("    (none listed)")
    return "\n".join(lines)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
