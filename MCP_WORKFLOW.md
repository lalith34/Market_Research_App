# MCP Workflow — Three Data Sources, One Briefing

How the three bundled MCP servers work **together** inside the research agent:
what each contributes, when each fires, how to run the workflow, and how to
verify and customize it.

> New to the servers themselves? See the per-server notes in
> [`src/market_research_agent/mcp_servers/`](src/market_research_agent/mcp_servers/).
> This doc is about orchestrating all three in one run.

---

## 1. The three servers

| # | Server (module) | Tool | Provides | Key? | Loaded |
|---|---|---|---|---|---|
| 1 | `hn_server` | `hn_search` | Recent news / developer & market sentiment (Hacker News) | none | **default-on** (`MRA_HN`) |
| 2 | `edgar_server` | `edgar_lookup` | Public-company status, ticker, exchange, industry, SEC filings | none | `--mcp-config` |
| 3 | `datastore_server` | `internal_lookup` | Proprietary pricing / market-share / win-loss intel (SQLite) | none | `--mcp-config` |

`hn_search` is on by default; `edgar_lookup` and `internal_lookup` come from
[`mcp_servers.bundled.json`](mcp_servers.bundled.json). Together with the two
built-ins (`web_search`, `fetch_page`), a full run gives the agent **five tools**.

> Why isn't HN in `bundled.json`? Because it already loads by default — listing
> it again would spawn a second `hn_search` and collide. The config adds only the
> two non-default servers.

---

## 2. The workflow

```
                    market-research "<target>" --mcp-config mcp_servers.bundled.json
                                              │
                    ┌─────────────────────────┴───────────────────────────┐
                    │ build_tools(): web_search, fetch_page, hn_search      │  ← hn_search default-on
                    │ + _load_mcp_config(bundled.json): edgar_lookup,       │  ← spawned as stdio
                    │   internal_lookup                                     │     subprocesses
                    └─────────────────────────┬───────────────────────────┘
                                              │  all 5 tools bound to the LLM
                                              ▼
   ┌─────────────┐     ┌──────────────────────────────────────────────────────────────┐
   │  discover   │ ──▶ │  research (per competitor) — the tool loop                     │
   │ web_search  │     │                                                                │
   │ → top N     │     │   LLM picks tools per the research prompt, which now lists     │
   └─────────────┘     │   ALL bound tools and says "prefer a specialized tool":        │
                       │                                                                │
                       │   • edgar_lookup(name)   → public/private, ticker, filings     │
                       │   • internal_lookup(name)→ proprietary pricing & win/loss       │
                       │   • web_search / fetch_page → pricing, features, positioning   │
                       │   • hn_search(name)      → recent news/sentiment (if relevant) │
                       │                                                                │
                       │   evidence trail ─▶ structured extraction (CompetitorProfile)  │
                       └──────────────────────────────┬───────────────────────────────┘
                                                      ▼
                       ┌──────────────────────────────────────────────────────────────┐
                       │  synthesize → exec summary + SWOT + briefing (md / html)       │
                       └──────────────────────────────────────────────────────────────┘
```

**The key enabler:** the research prompt advertises *every* bound tool
(`graph.py:_format_tools`) and instructs the model to **prefer a specialized tool
when its description fits**. Without that, the MCP tools load but never get called.

### What each tool enriches in the final briefing

| Tool | Feeds these parts of the briefing |
|---|---|
| `edgar_lookup` | The **public/private badge** (ticker/exchange) and recent-news (SEC filings) |
| `internal_lookup` | **Strengths/weaknesses** and pricing — grounded in first-party win/loss notes |
| `hn_search` | **Recent news** and market sentiment |
| `web_search` + `fetch_page` | Pricing tables, features, positioning, HQ country, the rest |

---

## 3. Run it

```bash
cd /path/to/Market_Research_App
source .venv/bin/activate

# All three MCP servers + the two built-ins, deterministic competitor set:
market-research "Vegan Beauty Products" \
  --competitors-list "e.l.f. Cosmetics, The Body Shop, Youth to the People" \
  --mcp-config mcp_servers.bundled.json \
  -o vegan_beauty.html 2> vegan_beauty.log

open vegan_beauty.html
```

- `--competitors-list` pins the three brands (skips discovery) so the run is
  deterministic and the internal datastore — which has sample rows for exactly
  these brands — is guaranteed to hit.
- `--mcp-config mcp_servers.bundled.json` adds `edgar_lookup` + `internal_lookup`.
- `2> vegan_beauty.log` captures the progress log for verification (next step).

---

## 4. Verify which tools fired

```bash
# Confirm the MCP servers loaded
grep "Loaded MCP" vegan_beauty.log
#  → Loaded MCP tools from mcp_servers.bundled.json: edgar_lookup, internal_lookup

# Count tool calls by type
grep -oE '· (web_search|fetch_page|hn_search|edgar_lookup|internal_lookup)' vegan_beauty.log \
  | sort | uniq -c
#  → e.g.  3 · edgar_lookup   3 · internal_lookup   5 · fetch_page   7 · web_search

# Prove the proprietary data reached the report
grep -oE 'supply-chain audit|ingredient transparency|enterprise-gifting' vegan_beauty.html
```

A healthy run shows `edgar_lookup` and `internal_lookup` firing ~once per
competitor, and internal sample phrases appearing in the HTML. (`hn_search` may
be 0 — the model only calls it when recent-news/sentiment is relevant to the
target; that's expected, not a failure.)

### Offline pre-check (no API key / network)
```bash
python -c "from market_research_agent.config import Settings; \
from market_research_agent.tools import build_tools; \
from market_research_agent.cli import _load_mcp_config; \
print([t.name for t in build_tools(Settings()) + _load_mcp_config('mcp_servers.bundled.json')])"
# → ['web_search', 'fetch_page', 'hn_search', 'edgar_lookup', 'internal_lookup']
```

---

## 5. Customize the workflow

**Use your own internal database** (instead of the in-memory sample):
```bash
MRA_DATASTORE_DB=/path/to/your.db \
market-research "Notion" -n 3 --mcp-config mcp_servers.bundled.json -o out.html
```
Schema expected by `datastore_server`:
`competitor_intel(name, segment, pricing_intel, market_share, win_loss)`.
For Postgres/Snowflake/Salesforce, copy `datastore_server.py` and swap `_connect()`.

**Add more servers** — append to the JSON config; they're loaded the same way:
```json
{
  "sec_edgar":          { "command": "python", "args": ["-m", "market_research_agent.mcp_servers.edgar_server"], "transport": "stdio" },
  "internal_datastore": { "command": "python", "args": ["-m", "market_research_agent.mcp_servers.datastore_server"], "transport": "stdio" },
  "crunchbase":         { "command": "npx", "args": ["-y", "@you/crunchbase-mcp"], "transport": "stdio", "env": { "CRUNCHBASE_API_KEY": "..." } }
}
```

**Disable a default** — `MRA_HN=false` drops `hn_search` from the toolset.

**Run a server standalone** (debugging):
```bash
python -m market_research_agent.mcp_servers.edgar_server       # stdio server
python -c "from market_research_agent.mcp_servers.edgar_server import edgar_lookup; print(edgar_lookup('e.l.f. Beauty'))"
```

---

## 6. How it's wired (code map)

| Step | Where |
|---|---|
| Declare servers | [`mcp_servers.bundled.json`](mcp_servers.bundled.json) |
| Parse `--mcp-config`, load tools | `cli.py:_load_mcp_config` → `tools/mcp.py:load_mcp_tools` |
| Spawn servers over stdio, discover tools | `MultiServerMCPClient` (langchain-mcp-adapters) |
| Default-load `hn_search` | `tools/__init__.py:build_tools` → `tools/mcp.py:load_bundled_tools` |
| Advertise all tools to the model | `graph.py:_format_tools` + `prompts.py:RESEARCH_SYSTEM` |
| Invoke tools (sync + async/MCP) | `graph.py:_invoke_tool` / `_tool_text` |
| Each server's logic | `mcp_servers/{hn,edgar,datastore}_server.py` |
