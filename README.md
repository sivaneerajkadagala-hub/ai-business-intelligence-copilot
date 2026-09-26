# AI Business Intelligence Copilot

An enterprise-style, full-stack Business Intelligence platform. Upload business
data, profile and clean it, explore it through KPIs and drag-and-drop
dashboards, ask natural-language questions compiled to **validated SQL**, and
get AI-generated insights, anomaly detection, and Holt-Winters forecasts.

## What it does

- **Dataset pipeline** — CSV/XLSX upload → type inference → physical typed
  tables → per-column profiling (nulls, distinct, distribution, outliers) →
  quality scores → cleaning ops as **new versions** (originals never mutated).
- **Analytics** — aggregation engine (sum/avg/count/min/max × whitelisted
  filters × date bucketing), KPI definitions with period deltas + target
  progress, live Recharts dashboard.
- **BI Copilot** — natural-language questions → intent extraction → SQL via a
  deterministic rule engine *or* a real LLM → `sqlglot` AST validation → safe
  execution → auto charts + grounded explanations. Ask "top 5 categories by
  revenue", "any anomalies?", or "forecast next 4 months".
- **AI insights** — detrended z-score anomaly detection (IQR fallback),
  pure-numpy Holt-Winters/Holt/naive forecasting with ~80% CIs, and a
  one-click insight generator (trend, top/laggard, anomalies, data quality).
- **Workspace** — drag-and-drop dashboard builder, saved-query library
  (re-validated before every run), PDF reports + sanitized CSV export,
  full audit trail.

## Architecture

```
frontend/     Next.js 16 (App Router, proxy.ts route guard, TanStack Query)
backend/      FastAPI — layered: routes → services → SQLAlchemy models
              services/ai: schema_context · intent · rule_engine · nl2sql
              llm_provider · sql_validator (sqlglot) · copilot · explainer
              anomalies · forecast · insights
database/     init: `public` schema (platform) + `data` schema + bi_reader role
docker/       multi-stage Dockerfiles · docker-compose.yml at root
```

### The SQL safety model

Every query — LLM-written or rule-engine — passes the same gauntlet:

1. Generated only from **schema metadata** the user can see (table + column
   allowlist, sample values).
2. **sqlglot AST validation**: SELECT-only, single statement, no DDL/DML/`COPY`
   /dangerous functions, tables ⊆ allowed set, columns ⊆ allowed set,
   `LIMIT ≤ 5000` enforced.
3. Executed read-only with a 10s `statement_timeout` on Postgres.
4. All executions logged to `query_history` (status, rows, duration, source).

### Auth & authorization

Argon2id password hashing, 15-min JWT access tokens, rotating refresh-token
cookies with **reuse detection** (stolen-token replay revokes the family),
three roles (`admin` / `analyst` / `viewer`) enforced at route *and* resource
level, and an audit log on every sensitive action.

## Demo accounts

Seeded on startup (`python -m seed.run`, idempotent). Password: `Demo1234!`

| Email | Role |
|-------|------|
| `admin@bicopilot.dev` | admin |
| `analyst@bicopilot.dev` | analyst |
| `viewer@bicopilot.dev` | viewer |

Seeding also creates realistic datasets — **Sales (6,131 rows, 25 months, with
injected anomalies)**, Customers, Products, Orders.

## Quick start

### Docker

```bash
cp .env.example .env        # dev defaults work out of the box
docker compose up --build   # db migrates + seeds automatically
```

- Frontend: http://localhost:3000 · API: http://localhost:8000 · Swagger: `/api/docs`
- Requires Docker Desktop (WSL2 engine on Windows).

### Local development

```bash
# Backend — SQLite fallback works out of the box
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements-dev.txt
DATABASE_URL="sqlite+pysqlite:///./dev.db" uvicorn app.main:app --port 8000

# Seed demo accounts + datasets (same DATABASE_URL)
python -m seed.run

# Frontend
cd frontend && npm install && npm run dev      # http://localhost:3000
```

Point `DATABASE_URL` at Postgres (see `.env.example`) and run
`alembic upgrade head` for the real deployment path.

## Testing

```bash
cd backend && pytest          # 79 unit/integration tests — auth, datasets,
                              # analytics, copilot, insights, workspace, audit
cd frontend && npm run lint && npm run build
python tests/e2e/smoke.py     # end-to-end smoke (needs backend on :8000)
```

## Environment variables

See [.env.example](.env.example). Highlights:

| Var | Purpose |
|-----|---------|
| `LLM_PROVIDER` | `none` (default — deterministic engine) / `anthropic` / `openai` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | used only when the matching provider is set |
| `SECRET_KEY` | long random value for any non-local use |
| `BI_READER_*` | read-only DB role for AI-generated SQL |
| `DATABASE_URL` | Postgres; falls back to SQLite if unset |
| `MAX_UPLOAD_MB`, `MAX_RESULT_ROWS` | upload/query guardrails |

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 0–3 | Architecture, scaffold, auth/RBAC, dataset pipeline | Done |
| 4 | Analytics engine, KPIs, seeded data, live dashboard | Done |
| 5 | Copilot: NL→SQL, sqlglot validation, chat UI | Done |
| 6 | Anomaly detection, forecasting, insight engine | Done |
| 7 | Dashboard builder, saved queries, PDF/CSV reports | Done |
| 8 | Audit viewer, multi-turn copilot, pin-to-dashboard, docs | Done |
| 9 | Background jobs, notifications, data-source connectors | Planned |
| 10 | CI/CD hardening, deployment, final polish | Planned |
