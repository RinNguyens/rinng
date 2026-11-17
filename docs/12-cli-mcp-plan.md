# 12 — CLI and MCP access plan

Written 2026-11-17. Goal: anyone can use rinng's analysis **without the web app**, either from a
terminal (`rinng summary BTC`) or from an AI client over MCP (Claude Code, Claude Desktop, Cursor…),
ideally with one install command and no backfill.

Status (2026-11-17): phases A–D done; E done except PyPI / MCP registry publishing.
- A: `rinng.config` resolution, `rinng[dashboard]` extra; ta-lib has wheels everywhere (no manual step).
- B: `rinng.service.Rinng`, thin `web/app.py`, `/api/status`, offline mode.
- C: `search`, `summary`, `signal`, `lens`, `news`, `status`; compact views in `rinng.views`, with a
  stale-data warning when stored candles lag more than 3 bars.
- D: `rinng mcp` on the official SDK (`mcp` 2.x, `MCPServer`), a core dependency. Deviation: tools
  return structured content plus a text summary and the JSON, without a declared output schema.
- Decisions taken: `mcp` in core, `streamlit`/`plotly` in the `dashboard` extra, git-only install
  for now (PyPI name `rinng` is free).

## 1. Where things stand

| Area | Today | Gap |
|---|---|---|
| CLI (`src/rinng/cli.py`) | Data ops only: `check`, `backfill`, `curate`, `resample`, `validate`, `analyze`, `backtest`, `collect`, `live`, `web`, `dashboard`, `vpchart` | No command answers "what does the market look like for X?". `analyze` writes Parquet, prints row counts |
| Analysis for one coin | Lives inside closures in `create_app()` (`web/app.py:57-320`): `candles()` with REST fallback, `derivs()`, `/api/summary`, `/api/desk`, `/api/chart`, `/api/news`, plus the TTL cache | Cannot be called without FastAPI. CLI and MCP would have to copy it |
| MCP | None. `docs/06` §6 already recommends packaging our own functions as an MCP server, read-only | Whole feature |
| Install outside the repo | `DEFAULT_CONFIG = Path("configs/instruments.yaml")` (relative to cwd) and the YAML is not in the wheel; `data_dir: data` is relative to cwd | `uvx …rinng` from another folder crashes on startup |
| Dependencies | Core pulls `streamlit` and `plotly` (only for `dashboard`/`vpchart`) | Slow, heavy install for CLI/MCP users |

What already works in our favour: `catalog.resolve()` / `catalog.search()` cover ~790 USDT perps;
`candles()` and `derivs()` fall back to Binance/OKX REST when nothing is stored, so a fresh install can
analyse any coin immediately (shorter history, no liquidations).

## 2. Design

```
              ┌──────────── rinng.service.Rinng ────────────┐
web/app.py ──►│ candles · derivs · summary · desk · lens    │◄── cli.py (summary, signal, lens, news, search)
              │ news · search · status · TTL cache          │◄── mcp_server.py (tools, resources, prompts)
              └──────────────┬──────────────────────────────┘
                             ▼
          store (Parquet) ── REST fallback (Binance/OKX) ── analysis/* (unchanged)
```

Rules:

1. **One service layer, three front ends.** Web, CLI and MCP call the same methods and get the same
   numbers. The service raises `NotFound` / `BadRequest`; each front end maps them (HTTP 404/400,
   CLI exit code 2, MCP tool error).
2. **Read-only, no keys.** No tool places orders or touches accounts; the Solana relay is not exposed.
   Same guarantee as `docs/06` §9.
3. **Offline first, REST second.** Use curated data when it covers the window, otherwise REST. A
   `--offline` flag / `offline=True` refuses the network.
4. **Compact output for machines.** `--json` and MCP return verdicts, levels, events and stats, not
   2,000-candle arrays (candles only on request, capped). Every payload carries
   `schema_version`, `source` (`curated`/`live`) and `as_of`.
5. **Not advice.** Every human and MCP output ends with the same one-line disclaimer as the README.

## 3. Phases

Sizes as in `docs/09`: S / M / L, relative.

### Phase A — Runs from any folder (S)

Prerequisite for `uvx` and for MCP clients, which start the server from an arbitrary cwd.

1. Ship the default config inside the package: `src/rinng/config/instruments.yaml` (keep
   `configs/instruments.yaml` as the dev copy or make it the same file).
2. Config resolution: `--config` → `RINNG_CONFIG` → `./configs/instruments.yaml` if it exists →
   bundled default.
3. Data dir resolution: `RINNG_DATA` → config `data_dir` (relative paths resolved against the
   config file's folder, not cwd) → `~/.rinng/data` for the bundled config.
4. Move `streamlit` (and `plotly` if only `viz/` uses it) to an extra `rinng[dashboard]`;
   `dashboard`/`vpchart` print an install hint when missing.
5. Verify `ta-lib` 0.8.3 installs from wheels (no system C library) on macOS arm64, Linux x86_64,
   Windows. If not, document it as the one manual step.

**Done when:** in an empty temp folder,
`uvx --from git+https://github.com/RinNguyens/rinng rinng check` works, and existing tests pass.

### Phase B — Service layer (M)

1. New `src/rinng/service.py` with `class Rinng(settings, hub=None, catalog=None)`. Move from
   `create_app()`: `cached`, `instrument`, `venue`, `from_1m`, `candles`, `derivs`, and the bodies of
   `summary`, `desk`, `chart` (lens), `news`, `instruments`.
2. Symbol normalisation in one place: `BTC`, `btc`, `BTCUSDT`, `BTC/USDT`, `BTC-USDT-PERP` all resolve
   (reuse `catalog.search` ranking, exact base match first; ambiguous → `BadRequest` listing matches).
3. `web/app.py` becomes thin routes over `Rinng`. No API shape change; the React app must not notice.
4. Add `status()`: configured instruments, last stored 1m bar per exchange, live or not.

**Done when:** `tests/test_web_summary.py` and the rest pass unchanged; new `tests/test_service.py`
covers resolution, curated-vs-REST choice (REST mocked with `httpx.MockTransport`), and error mapping.

> Commit or stash the current uncommitted work in `web/app.py` and `web/lenses.py` first: this phase
> rewrites `create_app()`.

### Phase C — Analysis commands in the CLI (M)

| Command | Prints | Source |
|---|---|---|
| `rinng search sol` | id, name, Binance/OKX symbols, stored or not | `search` |
| `rinng summary BTC [--exchange okx]` | price + 24h/7d change, funding, OI change, long/short, 4h structure (trend, last BOS/CHoCH), weekly POC/VA, nearest liquidity, Wyckoff phase, momentum | `summary` |
| `rinng signal BTC` | verdict (lean, score), table of agent votes with reasons, long/short scenarios (entry zone, invalidation, targets), forecast quantiles and walk-forward hit rate | `desk` |
| `rinng lens BTC --lens structure --tf 4h --days 180` | the lens's recent events and levels (no candles; `--candles N` to add) | `chart` |
| `rinng news [--coin BTC] [--limit 20]` | scored headlines + 24h outlook | `news` |
| `rinng status` | what is stored locally, freshness, whether a collector is running | `status` |

Shared options: `--exchange`, `--json`, `--offline`, `--config`. Human output via `rich` tables (typer
already depends on it); `--json` prints the service payload. Exit codes: 0 ok, 2 bad input or unknown
symbol, 3 not enough data, 4 network error.

**Done when:** each command has a `typer.testing.CliRunner` test on fixture data, `--json` output
validates against a pydantic model, and `rinng signal BTC` on a fresh install (no data) returns in
under ~10 s.

### Phase D — MCP server (M)

Official Python SDK (`mcp`, `FastMCP`). Entry point `rinng mcp` (stdio, default) and
`rinng mcp --http --port 8765` (streamable HTTP, binds 127.0.0.1 only).

**Tools** — all annotated `readOnlyHint: true`, `openWorldHint: true`:

| Tool | Args | Returns |
|---|---|---|
| `search_instruments` | `query`, `limit=10` | matches with ids |
| `market_summary` | `symbol`, `exchange="binance"` | the `summary` blocks |
| `trade_desk` | `symbol`, `exchange` | verdict, votes, scenarios, forecast + stats (no candles) |
| `analyze_lens` | `symbol`, `lens`, `timeframe="4h"`, `days=180`, `exchange` | lens events/levels |
| `get_candles` | `symbol`, `timeframe`, `limit≤500`, `exchange` | columnar OHLCV |
| `crypto_news` | `coin=None`, `limit=20` | headlines, sentiment, outlook |
| `data_status` | — | `status()` |

Each tool returns structured content (pydantic output model, so clients get an output schema) plus a
3–6 line text summary the model can quote.

**Resources:** `rinng://instruments` (configured list), `rinng://methods/{lens}` — short explanation
of each method, its inputs and known weaknesses (condensed from `docs/04`), so the model interprets
the numbers instead of guessing.

**Prompts:** `analyze_coin(symbol)` — call `market_summary` then `trade_desk`, present both sides,
state data source and uncertainty, no position sizing, no advice.

Implementation notes:

- stdout is the protocol channel: all logging goes to stderr; silence anything that prints.
- Analysis is sync and CPU-bound: run it in a worker thread (`anyio.to_thread.run_sync`) so the
  server stays responsive; one `Rinng` instance per process so the cache is shared.
- News titles are third-party text: return them in a field marked as untrusted
  (`docs/06` §6 on prompt injection) and never inside instructions.
- Keep each result under ~20 KB; round floats, ISO timestamps.
- OKX needs IPv4 on some machines — the existing httpx transport already forces it; keep it.

**Done when:** in-memory client/server tests (SDK test client) list the 7 tools with schemas and call
each against a fake `Rinng`; MCP Inspector (`npx @modelcontextprotocol/inspector uv run rinng mcp`)
lists and runs every tool; Claude Code answers "phân tích BTC" using `market_summary` + `trade_desk`.

### Phase E — Docs and distribution (S)

1. README: sections "Use from the terminal" and "Use with AI clients (MCP)" with copy-paste configs:

   ```bash
   # Claude Code
   claude mcp add rinng -- uvx --from git+https://github.com/RinNguyens/rinng rinng mcp
   ```

   ```json
   // Claude Desktop / Cursor: mcpServers
   "rinng": { "command": "uvx",
              "args": ["--from", "git+https://github.com/RinNguyens/rinng", "rinng", "mcp"] }
   ```

   From a local clone (uses its stored data): `uv --directory /path/to/rinng run rinng mcp`.
2. Optional: publish to PyPI (then `uvx rinng mcp`) and add a `server.json` for the MCP registry.
3. Tag `v0.2.0`; CI runs the new tests.

### Later (not in this plan)

Claude Code skill wrapping the prompt; `rinng watch` alerts; remote MCP with auth; exposing backtests
as a tool (needs stored data and is slow).

## 4. Order and risks

Order: A → B → C and D in parallel (both only need B) → E.

| Risk | Mitigation |
|---|---|
| Refactoring `create_app()` changes web behaviour | Phase B keeps routes identical; web tests + a manual pass on the desk page |
| `ta-lib` has no wheel on some platform | Check in phase A; document `brew install ta-lib` / apt fallback |
| REST-only users get thin history (forecast needs ~2,000 bars) | Service already fetches up to `MAX_BARS`; `trade_desk` reports `source` and sample size so the model can say so |
| Rate limits when an agent loops over many coins | Existing throttle + TTL cache; cap `search` and refuse >1 request/s per symbol in the MCP layer if needed |
| Models present the verdict as advice | Disclaimer in every payload, prompt template says no advice, methods resource lists weaknesses |

## 5. Decisions needed

1. Publish to PyPI, or git-only install?
2. Move `streamlit` to an extra (smaller install, `rinng dashboard` needs `rinng[dashboard]`)?
3. `mcp` as a core dependency (simplest install) or `rinng[mcp]`?
