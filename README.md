# Market Research Agent — Competitor Analysis

An autonomous agent that takes a **company, product, or market category**,
researches the competitors / leading brands using **web search + document
retrieval**, extracts key insights (pricing, features, market positioning,
recent news, and **public/private + HQ-country** status), and produces a
**structured competitive-analysis briefing** in **Markdown or styled HTML**.
Point it at `"Notion"` to map a company's rivals, or at `"Healthy Soda"` to map
a whole category you're entering.

Built with **LangGraph**. LLM runs on **Nebius AI Studio** (OpenAI-compatible,
default `deepseek-ai/DeepSeek-V3.2`). Search defaults to **DuckDuckGo** (no API
key). Engineers can plug in custom **MCP tool servers** for extra data sources —
three working ones ship (Hacker News, SEC EDGAR, internal SQLite intel).

```
target ─▶ [discover] ─▶ [research] ─▶ [synthesize] ─▶ briefing.(md|html)
           competitors   per-competitor   draft → reflect
           (+ optional    tool loop +      (critique/revise)
            human review)  extraction       + rendered tables
```

Every run reports **cost / latency / reliability** metrics (tokens, time, tool
calls, and failure-mode counts) — see the footer printed after each run.

## Documentation

| Doc | What it's for |
|---|---|
| `README.md` (this file) | Setup, commands, configuration, reference. |
| [`MCP_WORKFLOW.md`](MCP_WORKFLOW.md) | End-to-end workflow for the three bundled MCP servers. |

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp .env.example .env          # then add your NEBIUS_API_KEY

# Run it
market-research "Notion" --competitors 3 --output samples/notion_briefing.md
# or, without installing the console script:
python -m market_research_agent.cli "Linear" -n 3

# Output a styled, browser-viewable HTML report (format inferred from .html)
market-research "Notion" -n 3 --output samples/notion_briefing.html
# ...or force a format regardless of the filename
market-research "Notion" -n 3 --format html -o report.txt

# Analyze a whole market category (not just one company)
market-research "Healthy Soda" -n 3 --mode category

# Pin the exact competitors and skip auto-discovery (deterministic / scriptable)
market-research "Notion" --competitors-list "Coda, Linear, Obsidian"

# Human-in-the-loop: approve/edit the competitor list before researching
market-research "Notion" -n 3 --review

# Skip the reflection (Draft→Critique→Revise) pass for a faster/cheaper run
market-research "Notion" -n 3 --no-reflect
```

Output is written to the file given by `--output`, or printed to stdout. Choose
the format with `--format md|html` (or let it infer from the `--output`
extension). The **HTML** report is a self-contained file — a color-coded 2×2
SWOT grid, styled pricing table, and collapsible per-competitor sources — that
opens in any browser (use the browser's *Print to PDF* to share). See
[`samples/notion_briefing.md`](samples/notion_briefing.md) and
[`samples/notion_briefing.html`](samples/notion_briefing.html) for example output.

## All runnable commands

Every command for setting up, running, and testing the app. Run these from the
project root with the virtualenv activated (`source .venv/bin/activate`).

```bash
# ── Setup (one time) ───────────────────────────────────────────────
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # installs deps incl. MCP runtime
pip install -e .                        # installs the `market-research` command
cp .env.example .env                    # then edit .env and add NEBIUS_API_KEY

# ── Run: basic ─────────────────────────────────────────────────────
market-research "Notion"                                  # 3 competitors, print to stdout
market-research "Notion" -n 5                             # research 5 competitors
python -m market_research_agent.cli "Notion" -n 3         # no console script needed

# ── Run: output formats ────────────────────────────────────────────
market-research "Notion" -n 3 -o briefing.md              # Markdown (inferred)
market-research "Notion" -n 3 -o briefing.html            # styled HTML (inferred)
market-research "Notion" -n 3 --format html -o report.txt # force HTML regardless of name
market-research "Notion" -n 3 --format md                 # force Markdown to stdout

# ── Run: target interpretation ─────────────────────────────────────
market-research "Healthy Soda" -n 3 --mode category       # treat target as a market
market-research "Notion" --mode brand                     # treat target as one company
market-research "Notion" --competitors-list "Coda, Linear, Obsidian"  # pin list, skip discovery

# ── Run: model / search backend ────────────────────────────────────
market-research "Notion" -m meta-llama/Llama-3.3-70B-Instruct   # override model
market-research "Notion" --search ddg                     # force DuckDuckGo
market-research "Notion" --search tavily                  # force Tavily (needs TAVILY_API_KEY)

# ── Run: pipeline toggles ──────────────────────────────────────────
market-research "Notion" -n 3 --review                    # human-in-the-loop competitor review
market-research "Notion" -n 3 --no-reflect                # skip Draft→Critique→Revise (faster/cheaper)
market-research "Notion" -n 3 --no-swot                   # omit the SWOT section
market-research "Notion" -n 3 -q                          # suppress progress logs

# ── Run: with custom MCP tool servers ──────────────────────────────
market-research "Notion" -n 3 --mcp-config mcp_servers.example.json -o out.html
market-research "Vegan Beauty Products" --mode category -n 3 \
  --mcp-config mcp_servers.bundled.json -o out.html       # adds SEC EDGAR + internal intel
python -m market_research_agent.mcp_servers.hn_server         # bundled Hacker News server
python -m market_research_agent.mcp_servers.edgar_server      # bundled SEC EDGAR server
python -m market_research_agent.mcp_servers.datastore_server  # bundled internal-intel server

# ── Environment toggles (prefix any run) ───────────────────────────
MRA_HN=false market-research "Notion" -n 3                # disable the default Hacker News tool
MRA_REFLECTION=false market-research "Notion" -n 3        # same as --no-reflect, via env
MRA_MAX_COMPETITORS=5 market-research "Notion"            # same as -n 5, via env

# ── Tests ──────────────────────────────────────────────────────────
python -m pytest -q                                       # full offline suite (no API key/network)
python -m pytest -q tests/test_smoke.py                   # the smoke tests explicitly

# ── Help ───────────────────────────────────────────────────────────
market-research --help                                    # full flag reference
```

## How it works

| Stage | Node | What it does |
|---|---|---|
| 1 | `discover` | Searches the web with **mode-aware seed queries** (brand vs. category) and uses the LLM to return a clean, deduped list of players (`CompetitorList`) — or skips straight to a **caller-pinned list** (`--competitors-list`). Optionally **pauses for human review** (`--review`). |
| 2 | `research` | For each competitor, runs a **bounded, loop-guarded tool-calling loop** (`web_search` + `fetch_page`), then extracts a structured `CompetitorProfile` from the full evidence trail. |
| 3 | `synthesize` | Drafts an executive summary + key takeaways, runs a **Reflection pass** (Draft→Critique→Revise), builds a **target-focused SWOT**, then renders the full Markdown briefing (SWOT grid, pricing table, per-competitor profiles, sources). |

Structured extraction is **resilient to flaky open-model tool calling**: it tries
native structured output first and falls back to JSON-from-text parsing
(`extract.py`).

### Features

Beyond the core pipeline, the agent includes:

- **Reflection pattern** — synthesis self-critiques against the evidence and
  revises, catching unsupported claims and vague takeaways (`graph.py:_reflect`).
- **Target-focused SWOT** — a classic 2×2 (Strengths/Weaknesses internal,
  Opportunities/Threats external) for the *target*, grounded in the competitor
  research. Toggle with `--no-swot` / `MRA_SWOT`.
- **Human-in-the-loop** — `--review` pauses the graph after discovery (LangGraph
  `interrupt`) so a human approves or edits the competitor list before the
  expensive research stage runs.
- **Failure-mode hardening** — the tool loop guards against the classic failure
  modes: duplicate/looping calls are served from cache (no wasted tokens),
  hallucinated tool names are reported not run, tool errors are caught, and a
  no-progress round stops the loop early.
- **Public vs. private + HQ-country callout** — each competitor profile leads
  with **bold** badges: an ownership badge (*Publicly traded* with exchange +
  ticker, *Privately held*, or *not determined*) and a location badge
  (*US-based — United States*, *Non-US — {country}*, or *HQ: not determined*).
  The researcher hunts for both and the extractor only marks what the evidence
  supports (`schemas.py`).
- **Safety guardrails** (`guardrails.py`) — (1) **input validation**: the target
  is bounded in length and stripped of control characters that could smuggle
  instructions into prompts; (2) **SSRF protection**: `fetch_page` resolves each
  URL and refuses internal/non-public addresses (`localhost`, `127.0.0.1`,
  `10.x`, cloud-metadata `169.254.169.254`, `file://`, …), re-checking after
  redirects; (3) **prompt-injection hardening**: fetched page text is declared
  untrusted *data*, and the researcher is told never to obey instructions found
  inside it.
- **Cost / latency / reliability metrics** — `metrics.py` tracks tokens, wall-
  clock time, tool-call counts, and failure-mode counters, printed as a footer
  and returned in the result state under `metrics`.

## Configuration

All settings come from environment / `.env` (see `.env.example`):

| Var | Default | Meaning |
|---|---|---|
| `NEBIUS_API_KEY` | — | **Required.** Nebius AI Studio key. |
| `NEBIUS_BASE_URL` | `https://api.studio.nebius.com/v1/` | OpenAI-compatible endpoint. |
| `MRA_MODEL` | `deepseek-ai/DeepSeek-V3.2` | Any tool-calling model on Nebius. |
| `MRA_SEARCH` | `auto` | `auto` → Tavily if key set, else DuckDuckGo. Force with `ddg`/`tavily`. |
| `MRA_MODE` | `auto` | Read the target as `brand`, `category`, or `auto`-detect (also `--mode`). |
| `MRA_COMPETITORS` | — | Comma-separated names to research verbatim, skipping discovery (also `--competitors-list`). |
| `TAVILY_API_KEY` | — | Optional higher-quality search. |
| `MRA_MAX_COMPETITORS` | `3` | How many competitors to research. |
| `MRA_MAX_RESEARCH_STEPS` | `6` | Tool-loop budget per competitor. |
| `MRA_REFLECTION` | `true` | Run the Draft→Critique→Revise pass on the synthesis. |
| `MRA_MAX_REFLECTION_ROUNDS` | `1` | Reflection rounds. |
| `MRA_SWOT` | `true` | Include the target-focused SWOT section. |
| `MRA_HUMAN_REVIEW` | `false` | Pause for human approval of competitors (also `--review`). |
| `MRA_HN` | `true` | Load the bundled Hacker News MCP tool (`hn_search`). Needs MCP deps installed; degrades gracefully otherwise. |

> **Note:** Nebius is *not* a Claude provider — it hosts open-weight models
> (DeepSeek, Llama, Qwen, ...). Because the client is OpenAI-compatible, you can
> point `NEBIUS_BASE_URL`/`MRA_MODEL` at any compatible endpoint (Together,
> OpenRouter, vLLM, local) without code changes.

## Use as a library

```python
from market_research_agent import run_analysis, Settings

state = run_analysis("Stripe", Settings.from_env(), progress=print)
print(state["briefing"])
```

## Extending with MCP tools

Engineers can add data sources (Crunchbase, internal wikis, CRM, ...) as MCP
servers — they become normal tools the agent can call alongside `web_search`
and `fetch_page`. The MCP runtime ships in `requirements.txt`, so no extra
install is needed to wire in your own servers.

**From the CLI** — point `--mcp-config` at a servers JSON file:

```bash
market-research "Notion" -n 3 --mcp-config mcp_servers.example.json -o out.html
```

**From the library** — load the tools and pass them as `extra_tools`:

```python
import asyncio
from market_research_agent import run_analysis, Settings
from market_research_agent.tools.mcp import load_mcp_tools

extra = asyncio.run(load_mcp_tools("mcp_servers.example.json"))
state = run_analysis("Notion", Settings.from_env(), extra_tools=extra)
```

See [`mcp_servers.example.json`](mcp_servers.example.json) for the config shape.

### Bundled MCP servers

Three working MCP servers ship with the agent under
[`src/market_research_agent/mcp_servers/`](src/market_research_agent/mcp_servers/) —
each is both a usable data source and a reference implementation to copy:

| Server | Tool | Data | Key? |
|---|---|---|---|
| `hn_server` | `hn_search` | Hacker News (recent news / sentiment) | none |
| `edgar_server` | `edgar_lookup` | SEC EDGAR — public-company filings, ticker, exchange, industry | none |
| `datastore_server` | `internal_lookup` | Internal pricing / market-share / win-loss intel (SQLite) | none |

`hn_search` loads **by default**. Add the other two (which pair especially well
with the public/private callout and the vendor "use your own data" story) via
[`mcp_servers.bundled.json`](mcp_servers.bundled.json):

```bash
market-research "Vegan Beauty Products" --mode category -n 3 \
  --mcp-config mcp_servers.bundled.json -o out.html
```

- **`edgar_lookup`** confirms whether a competitor is a US public company and
  pulls its ticker/exchange/recent filings; a "not found" is a strong *private*
  signal. (SEC's free API — no key, just a User-Agent.)
- **`internal_lookup`** serves sample proprietary intel from an in-memory SQLite
  DB out of the box. Point `MRA_DATASTORE_DB` at a real SQLite file, or copy the
  module and swap `_connect()` for Postgres / Snowflake / Salesforce.

See [`MCP_WORKFLOW.md`](MCP_WORKFLOW.md) for the end-to-end workflow that runs all
three together — what each contributes, when each fires, and how to verify.

### Reference: Hacker News (`hn_search`)

**It loads by default.** The MCP deps are in `requirements.txt`, so every run
gets `hn_search` automatically (alongside `web_search` / `fetch_page`) — no
config or `extra_tools` needed:

```python
from market_research_agent import run_analysis, Settings

# hn_search is already wired in — nothing extra to pass
state = run_analysis("Notion", Settings.from_env(), progress=print)
```

Turn it off with `MRA_HN=false`. Run it standalone to inspect:
`python -m market_research_agent.mcp_servers.hn_server`.

> If MCP support is ever uninstalled, the agent prints a one-line note and
> continues with the core tools rather than failing.

## Project layout

```
src/market_research_agent/
  config.py      # env-driven Settings
  llm.py         # Nebius/OpenAI-compatible ChatOpenAI factory
  tools/         # web_search (DDG/Tavily), web_fetch (trafilatura), mcp loader
  schemas.py     # CompetitorProfile, PricingTier, CompetitorList (pydantic)
  prompts.py     # stage prompts
  extract.py     # robust structured-output helper (+ token capture)
  metrics.py     # cost / latency / reliability tracking
  graph.py       # LangGraph: discover -> research -> synthesize (+ reflection, HITL)
  briefing.py    # Markdown renderer
  html_report.py # Self-contained styled HTML renderer
  guardrails.py  # Input validation + SSRF-safe URL checks
  pipeline.py    # run_analysis() entrypoint (drives human-review interrupts)
  cli.py         # `market-research` command
samples/         # example briefings
tests/           # offline smoke tests
```

## Limitations

- Insights are model-extracted from public web pages — **verify before acting**.
- DuckDuckGo can rate-limit; for heavy use set `TAVILY_API_KEY`.
- Open models vary in tool-calling reliability; DeepSeek-V3.2 / Llama-3.3-70B are
  the most dependable defaults.
