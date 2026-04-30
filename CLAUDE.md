# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

Vibe-Trading is a natural-language finance research agent that ships as a Python backend (`agent/`) plus a React 19 web UI (`frontend/`). The backend exposes the same engine through three entrypoints:

- `agent/cli.py` — interactive TUI / one-shot CLI (`vibe-trading`, `vibe-trading run`)
- `agent/api_server.py` — FastAPI server with SSE streaming (`vibe-trading serve`)
- `agent/mcp_server.py` — MCP server exposing 17–22 tools over stdio/SSE (`vibe-trading-mcp`)

All three share the same ReAct agent loop, tool registry, skills, and backtest engines under `agent/src/` and `agent/backtest/`.

## Common commands

### Install (dev)

```bash
pip install -e ".[dev]"               # editable install with pytest extras
cp agent/.env.example agent/.env      # then uncomment one LLM provider block
```

### Run

```bash
vibe-trading                          # interactive TUI
vibe-trading run -p "your prompt"     # single run, prints JSON with --json
vibe-trading serve --port 8899        # FastAPI; serves frontend/dist if built
vibe-trading-mcp                      # MCP stdio server (--transport sse for HTTP)
```

Frontend dev (proxies API to `localhost:8899`):

```bash
cd frontend && npm install && npm run dev   # http://localhost:5899
cd frontend && npm run build                # produces dist/ for the API server to serve
```

### Tests

`pyproject.toml` pins `testpaths = ["agent/tests"]` and `pythonpath = ["agent"]`, so pytest must be run from the repo root.

```bash
pytest --ignore=agent/tests/e2e_backtest --tb=short -q   # what CI runs
pytest agent/tests/test_metrics.py                       # single file
pytest agent/tests/test_metrics.py::test_sharpe -q       # single test
pytest -m unit                                           # markers: unit | integration
```

CI (`.github/workflows/test.yml`) additionally runs `python -m py_compile` on the three entrypoints plus `src/agent/loop.py`, `src/tools/__init__.py`, and `backtest/runner.py`, then `npm ci && npm run build` in `frontend/`.

### Lint

Ruff is configured (`pyproject.toml`, `select = ["E","F","W"]`, line-length 120, `ignore = ["E501"]`). There is no pre-commit hook — run `ruff check agent` manually if needed.

## Architecture

### Three entrypoints, one engine

`cli.py`, `api_server.py`, and `mcp_server.py` all build the same `ToolRegistry` (`agent/src/tools/__init__.py`) and run prompts through `AgentLoop` (`agent/src/agent/loop.py`). When changing core behavior, verify it works in all three — the MCP server in particular bypasses the TUI/SSE layers.

### ReAct loop with 5-layer context compression

`agent/src/agent/loop.py` is the heart of the agent. It implements:

- **Layer 1 microcompact** — old `tool` messages collapsed to `[cleared]` once more than `KEEP_RECENT=3` exist.
- **Layer 2 context_collapse** — folds long text blocks (head + tail preserved) without an LLM call once tokens exceed `COLLAPSE_THRESHOLD` (≈70% of `TOKEN_THRESHOLD`, default 40k).
- **Layer 3 auto_compact** — LLM-driven structured summary with a `TAIL_TOKEN_BUDGET=20_000` tail-protection window.
- **Layer 4** — the agent can voluntarily call the `compact` tool to trigger Layer 3.
- **Layer 5 iterative update** — subsequent compactions update the previous summary instead of starting from scratch.

The loop also batches **consecutive readonly tools** (`is_readonly = True`, default on `BaseTool`) onto a thread pool — keep `is_readonly = False` for any tool that mutates filesystem/state, otherwise it can run in parallel with itself.

`TOKEN_THRESHOLD` is tunable via env var.

### Tool auto-discovery

`src/tools/__init__.py::build_registry()` imports every module in `src/tools/`, walks `BaseTool.__subclasses__()`, and registers any class with a non-empty `name`. To add a tool:

1. Drop a file in `agent/src/tools/` containing a `BaseTool` subclass.
2. Set `name`, `description`, `parameters` (JSON Schema), and `is_readonly`.
3. Override `check_available()` → `False` to silently skip when optional deps are missing.

`RememberTool` is special-cased so all tools share a single `PersistentMemory` instance.

### Skills (progressive disclosure)

`agent/src/skills/<category>/<skill-name>/SKILL.md` (71 skills across 7 categories: `data-source`, `strategy`, `analysis`, `asset-class`, `crypto`, `flow`, `tool`). The system prompt only injects one-line summaries from frontmatter; full bodies load on demand via the `load_skill` tool (`SkillsLoader.get_content`).

User-created/patched skills live at `~/.vibe-trading/skills/user/` and **override bundled skills with the same name** (`SkillsLoader._load`). The `skill_writer_tool` provides save/patch/delete CRUD against this user dir.

### Backtest engine + loader fallback

`agent/backtest/`:

- `engines/` — 7 market engines (`china_a`, `global_equity`, `crypto`, `china_futures`, `global_futures`, `forex`, `options_portfolio`) plus a `composite` cross-market engine. All inherit from `engines/base.py::BaseEngine`; the shared `run_backtest()` does data load → signal generation → optimizer-aware target weights → bar-by-bar execution with per-market rule hooks → metrics. Override market-rule methods, not the loop.
- `loaders/` — implement `loaders/base.py::DataLoader` Protocol, decorate the class with `@register` from `loaders/registry.py`. Fallback chains live in `FALLBACK_CHAINS` (e.g. `a_share: [tushare, akshare]`, `hk_equity: [yfinance, futu, akshare]`). `resolve_loader(market)` walks the chain calling `is_available()`.
- `optimizers/` — `BaseOptimizer` subclasses (MVO, equal vol, max diversification, risk parity).
- `runner.py`, `metrics.py`, `validation.py` — orchestration, 15+ metrics, Monte Carlo / Bootstrap CI / Walk-Forward.

### Swarm (multi-agent DAG)

`agent/config/swarm/*.yaml` (29 presets) defines agents + DAG. Runtime in `agent/src/swarm/runtime.py` with worker pool (`worker.py`), task store (`task_store.py`), and SSE event mailbox (`mailbox.py`). Streamed via `/swarm/runs/{id}/events` from the API server.

### Persistent state layout

- `~/.vibe-trading/memory/` — file-backed `PersistentMemory` (cross-session remember/recall).
- `~/.vibe-trading/skills/user/` — user-created/patched skills.
- `agent/runs/` — per-run trace, code, artifacts (Docker mounts `vibe-runs` here).
- `agent/sessions/` — multi-turn chat + FTS5 search index (Docker mounts `vibe-sessions`).

When working with file paths inside tools, use `agent/src/tools/path_utils.py::safe_path` — path-containment is enforced and bypassing it is a security regression (see news 2026-04-22).

### Shadow Account pipeline

`agent/src/shadow_account/` is a self-contained pipeline (extractor → backtester → reporter → scanner) wired into 4 MCP tools and surfaced in the web UI. Templates for HTML/PDF reports live in `templates/`; `pyproject.toml`'s `package-data` ships them in the wheel — keep that list in sync when adding template files.

### Frontend

React 19 + Vite + TypeScript + Tailwind + Zustand + ECharts. `frontend/vite.config.ts` proxies all backend routes (`/run`, `/runs`, `/health`, `/sessions`, `/skills`, `/swarm/*`, `/upload`, `/api`, `/system`, `/shadow-reports`) to `http://localhost:8899` during dev. Production: `npm run build` → API server serves `dist/` as static files. Route-level lazy loading is in place (initial bundle 262KB) — preserve it when adding pages.

## Conventions (from CONTRIBUTING.md)

- Python 3.11+, Google-style docstrings, type hints encouraged.
- File size: aim < 400 lines, hard ceiling 800.
- No hardcoded config — use `.env`, YAML, or constants.
- Delete unused code rather than commenting it out.
- OKX symbols use `BTC-USDT` (hyphen, uppercase).
- UI strings are English; LLM output mirrors the user's language.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`).
- **Protected modules** — open an issue before modifying `agent/src/agent/`, `agent/src/session/`, or `agent/src/providers/`.

## When adding new code

- **New skill** → drop a `SKILL.md` (with frontmatter `name` / `description` / `category`) in `agent/src/skills/<category>/<skill-name>/`. No registration needed.
- **New swarm preset** → YAML in `agent/config/swarm/`. No registration needed.
- **New data source** → implement `DataLoader` Protocol, add `@register`, append to the relevant `FALLBACK_CHAINS` entry in `loaders/registry.py`, and add it to `_loader_modules` in `_ensure_registered()`.
- **New agent tool** → subclass `BaseTool` in `agent/src/tools/`. Discovery is automatic; gate optional deps via `check_available()`.
- **New MCP tool** → register it in `agent/mcp_server.py` and update the SKILL.md tool count + table in `agent/SKILL.md`.
- **New backtest engine** → subclass `engines/base.py::BaseEngine`, override market-rule hooks, add tests under `agent/tests/test_<market>_engine.py`.
