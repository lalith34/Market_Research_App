"""Internal data-store MCP server — reference for proprietary data sources.

Exposes an `internal_lookup` tool over a SQLite database of internal competitive
intelligence: your own pricing intel, market-share estimates, and win/loss notes
(the kind of evidence that turns a generic "weakness" into a sourced one). This
is the data a research vendor actually has and the web does not.

Out of the box it serves a small **sample** dataset from an in-memory DB so the
demo runs with zero setup. Point `MRA_DATASTORE_DB` at a real SQLite file to use
your own data — or copy this module and swap `_connect()` for a Postgres /
Snowflake / Salesforce client to wire in a live source.

Run standalone:
    python -m market_research_agent.mcp_servers.datastore_server
"""
from __future__ import annotations

import os
import sqlite3

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The datastore MCP server requires the MCP SDK: pip install mcp"
    ) from exc

mcp = FastMCP("internal_datastore")

# Fictional sample intel, clearly labelled. Replace by pointing MRA_DATASTORE_DB
# at a real database (same schema) or adapting _connect().
_SAMPLE_ROWS = [
    ("e.l.f. Cosmetics", "Mass-market vegan beauty",
     "Undercuts us ~30% on entry SKUs", "Est. 8% of our addressable segment",
     "Lost 3 enterprise-gifting deals to them in Q1 on price."),
    ("The Body Shop", "Ethical/natural beauty",
     "Premium pricing, frequent promos", "Est. 5% share, declining",
     "Won 2 deals vs them citing our cleaner supply-chain audit."),
    ("Youth to the People", "Premium clean skincare",
     "Higher price point than us", "Est. 3% share, growing fast in DTC",
     "Strong on ingredient transparency — recurring loss reason in surveys."),
    ("Coda", "Docs/workspace",
     "Aggressive free tier", "Est. 6% of mid-market we target",
     "Lost 4 PLG deals; won back 1 on enterprise admin features."),
    ("Linear", "Issue tracking",
     "Flat per-seat, no free tier", "Niche but loyal",
     "Frequently cited by churned eng-led accounts."),
]

_conn: sqlite3.Connection | None = None


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS competitor_intel ("
        "name TEXT, segment TEXT, pricing_intel TEXT, market_share TEXT, win_loss TEXT)"
    )
    if conn.execute("SELECT COUNT(*) FROM competitor_intel").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO competitor_intel VALUES (?,?,?,?,?)", _SAMPLE_ROWS
        )
    conn.commit()


def _connect() -> sqlite3.Connection:
    """Open the data store. Real file if MRA_DATASTORE_DB is set, else seeded in-memory."""
    global _conn
    if _conn is None:
        db_path = os.getenv("MRA_DATASTORE_DB")
        if db_path:
            _conn = sqlite3.connect(db_path, check_same_thread=False)
            _seed(_conn)  # no-op if the table already has rows
        else:
            _conn = sqlite3.connect(":memory:", check_same_thread=False)
            _seed(_conn)
    return _conn


def _lookup(conn: sqlite3.Connection, company: str) -> str:
    """Pure query+format (unit-testable without the server)."""
    company = (company or "").strip()
    if not company:
        return "internal_lookup error: empty company."
    rows = conn.execute(
        "SELECT name, segment, pricing_intel, market_share, win_loss "
        "FROM competitor_intel WHERE name LIKE ? COLLATE NOCASE",
        (f"%{company}%",),
    ).fetchall()
    if not rows:
        return f"No internal intel on file for {company!r}."
    out = [f"Internal competitive intel for {company!r} (proprietary):"]
    for name, segment, pricing, share, winloss in rows:
        out += [
            f"- {name} — {segment}",
            f"    Pricing intel: {pricing}",
            f"    Market share: {share}",
            f"    Win/loss notes: {winloss}",
        ]
    return "\n".join(out)


@mcp.tool()
def internal_lookup(company: str) -> str:
    """Fetch internal/proprietary competitive intel for a company.

    Returns our own pricing intelligence, market-share estimates, and win/loss
    notes — evidence not available on the public web. Use to ground strengths,
    weaknesses, and positioning in first-party data.

    Args:
        company: Competitor name (partial matches allowed), e.g. "e.l.f.".
    """
    return _lookup(_connect(), company)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
