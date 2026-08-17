# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All backend work runs from `backend_api_python/`.

```bash
# Set up
cd backend_api_python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests (unit + contract only — skip integration/stress)
python -m pytest -m "not integration and not stress" --ignore=tests/release_gate -q

# Run a single test file
python -m pytest tests/test_strategy_v2_runtime.py -v

# Lint
ruff check app scripts tests

# Local dev server (requires PostgreSQL and Redis running)
python run.py

# Export OpenAPI spec after API changes
python scripts/export_openapi.py

# Validate production config before deployment
python scripts/check_production_config.py --env-file .env --env-file backend_api_python/.env

# Repository-level checks
python scripts/check_version.py
python scripts/check_mojibake.py
docker compose -f docker-compose.yml config -q
```

## Docker stack

```bash
# Source checkout — builds backend from local code, pulls frontend/mobile from GHCR
cp backend_api_python/env.example backend_api_python/.env
cp .env.example .env
docker compose up -d --build

# With hardened production overlay + observability
docker compose -f docker-compose.yml -f docker-compose.production.yml -f docker-compose.observability.yml up -d --build
```

Test markers: `integration` (requires live testnet credentials) and `stress` (long-running synthetic). The `tests/release_gate/` directory contains additional release-time checks that should not run in normal development.

## Architecture

QuantDinger is an open-source AI Trading OS. The same backend Docker image runs as six distinct processes — each with a specific and exclusive responsibility:

| Process | Command | Owns |
| --- | --- | --- |
| `backend` | Gunicorn + Flask | HTTP, auth, validation, durable command submission |
| `migration` | `app.commands.migrate` | Schema application, exits before services start |
| `trading-worker` | `app.commands.trading_worker` | Strategy runtimes, pending orders, grid fills, exchange sessions |
| `scheduler-worker` | `app.commands.scheduler` | Portfolio monitoring, payment scans, signal alert dispatch |
| `celery-worker` | Celery worker | Finite AI, backtest, report, and maintenance jobs |
| `celery-beat` | Celery beat | Periodic task dispatch |

**Critical ownership rules:**
- HTTP routes must never start trading threads or own long-running loops.
- Strategy lifecycle commands go through PostgreSQL `qd_strategy_commands`; the trading worker claims them with `SKIP LOCKED`.
- Long-lived loops (strategy execution, exchange polling, grid runtimes) belong in the trading worker.
- Finite, retryable, observable work belongs in Celery (`app/tasks/`).
- Cache Redis (`redis`) may evict; job Redis (`redis-jobs`) uses AOF + `noeviction`. Never route Celery through the cache Redis.

## Backend module ownership

| Directory | Owns | Must not contain |
| --- | --- | --- |
| `app/routes/` | HTTP parsing, auth checks, response shape | Exchange logic, trading loops, large DB transactions |
| `app/routes/agent_v1/` | Scoped agent/MCP API under `/api/agent/v1/` | Human-facing routes |
| `app/openapi/` | OpenAPI schemas, registration, export | Business logic |
| `app/services/` | Business workflows, use-case orchestration | Flask `request`/`g` except at route boundary |
| `app/services/live_trading/` | Exchange and broker adapters, normalized order API | Strategy lifecycle, user auth, HTTP responses |
| `app/services/strategy_v2/` | Strategy V2 contract, runtime, storage, live execution | Route parsing, UI formatting |
| `app/data_sources/` | Raw market data adapters | Order placement, account mutation |
| `app/data_providers/` | Dashboard/global market aggregation and cache policy | Trading decisions |
| `app/tasks/` | Finite Celery jobs | Long-lived loops |
| `app/workers/` | Long-lived worker process shells | HTTP request handling |
| `app/utils/` | Low-level DB, cache, auth, logging helpers | Feature workflows |
| `app/config/` | Environment-backed config | Runtime side effects |
| `migrations/` | SQL schema and seed data | Python runtime behavior |
| `mcp_server/` | Standalone MCP server package | Backend business logic |

## API conventions

Two distinct API surfaces with different auth and response envelopes:

**Human Web API** (`/api/...`) — user JWTs (`Authorization: Bearer <jwt>`):
```json
{ "code": 1, "msg": "success", "data": {} }   // success
{ "code": 0, "msg": "Error description", "data": null }  // error
```

**Agent Gateway** (`/api/agent/v1/...`) — agent tokens (`qd_agent_...`):
- Uses `message` (not `msg`) and `code: 0` on success (opposite of human API).
- Errors include `details` and `retriable` fields.

After changing API routes: regenerate the spec with `python scripts/export_openapi.py` and commit the updated `docs/api/openapi.yaml`. The CI runs `oasdiff` against the committed spec. Interactive docs are at `/api/docs/swagger` when `OPENAPI_ENABLED=true`.

## Where changes belong

| Change | Primary location | Also update |
| --- | --- | --- |
| New/modified HTTP endpoint | `app/routes/` | `app/openapi/`, tests, `docs/api/openapi.yaml` |
| New business workflow | `app/services/` | Focused service tests |
| New exchange or broker | `app/services/live_trading/` | `factory.py`, adapter tests |
| New market data source | `app/data_sources/` | `data_providers/`, cache keys, tests |
| New finite async task | `app/tasks/` | `celery_app.py`, queue routing |
| Long-lived process behavior | `app/workers/`, `app/commands/` | Compose command, health checks |
| Database schema change | `migrations/` | Release-gate tests |
| New MCP tool | `mcp_server/src/quantdinger_mcp/` | Agent Gateway scope, security tests |

## Git workflow

### Remote and fork

All work targets the personal fork: **https://github.com/alvinchow97/QuantDinger**

- The `origin` remote must always point to `https://github.com/alvinchow97/QuantDinger.git`.
- Always create branches from the fork's `main`, not from the upstream `OpenByteInc` repo.
- All PRs must be opened against `alvinchow97/QuantDinger`, never `OpenByteInc/QuantDinger`.

### Branch naming

Branches must use one of these exact prefixes:

| Prefix | When to use |
| --- | --- |
| `feat/` | new features |
| `fix/` | bug fixes |
| `docs/` | documentation only |
| `chore/` | maintenance, dependency bumps, tooling |
| `refactor/` | code restructuring without behavior change |
| `test/` | test additions or corrections |
| `ci/` | CI/CD configuration |
| `perf/` | performance improvements |
| `hotfix/` | urgent production fixes |
| `release/` | release preparation |

Use short, lowercase, hyphenated slugs: `feat/macd-indicator`, `fix/position-sizing-rounding`.

### Commit messages

Follow **Conventional Commits** format:

```
type(optional-scope)?: short description   ← max 100 chars, lowercase after colon

Optional longer body explaining WHY, not WHAT.
```

Allowed types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`, `style`, `build`

Rules:
- Description starts lowercase, no trailing period.
- Subject line max 100 characters.
- Body explains motivation, not mechanics.
- **Never include `Co-Authored-By: Claude`, `Generated with Claude`, or any mention of AI tooling** in commit messages.
- Avoid vague subjects like `fix: update`, `chore: changes`, `feat: misc`.

Examples:
```
feat(strategy_v2): add MACD crossover signal handler
fix(live_trading): correct Binance precision rounding on spot orders
docs: document agent gateway authentication flow
chore: bump ruff to 0.16.2
refactor(backtest): extract simulation loop into pipeline components
```

### Pull request workflow

```bash
# 1. Start from fork's latest main
git fetch origin
git checkout -b feat/your-feature origin/main

# 2. Work, commit following conventions above

# 3. Push to your fork
git push -u origin feat/your-feature

# 4. Open PR targeting alvinchow97/QuantDinger main
gh pr create \
  --repo alvinchow97/QuantDinger \
  --base main \
  --title "feat: your feature title" \
  --body "..."
```

PRs must include: what changed and why, how to test, and any backward-compatibility notes. Follow the PR template in `.github/PULL_REQUEST_TEMPLATE.md`. Keep PRs focused and reviewable.

The git hooks in `.githooks/` (active via `git config core.hooksPath .githooks`) enforce commit message format and remote validation automatically. Run `git log --oneline -5` to verify message format before pushing.

## High-risk legacy files (refactor targets, not extension points)

- `app/services/trading_executor.py`
- `app/services/backtest.py`
- `app/routes/ai_chat.py`, `app/routes/settings.py`, `app/routes/quick_trade.py`
- `app/services/pending_order_worker.py`

Do not add unrelated behavior to these files. When touching them, extract a small focused module.

## Key conventions

- **Language:** all code, comments, docstrings, logs, and module names must be English. Chinese is only allowed in user-facing localized text, prompt examples, and backward-compatible API fields.
- **Routes stay thin:** one screen, no exchange-specific logic, no inline transactions. If a route needs helpers, move them to a service first.
- **Services accept plain values:** no Flask `request` or `g` objects; return plain dicts or dataclasses.
- **Adapters know nothing about Flask or users:** exchange/broker adapters normalize external APIs into internal contracts.
- **Idempotency is required** for any state-mutating operation that may be retried (orders, strategy start/stop, backtests, USDT payment).
- **File size soft limits:** route modules ~400 lines, service modules ~800 lines, adapters ~900 lines.
- **OpenAPI is the source of truth** for the human API contract. High-risk mutations use typed request contracts in `app/openapi/schemas/high_risk.py`.
