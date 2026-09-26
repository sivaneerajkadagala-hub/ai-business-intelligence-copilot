# AI Business Intelligence Copilot

An enterprise-style, full-stack Business Intelligence platform. Upload business
data, profile and clean it, explore it through dashboards, ask natural-language
questions that are compiled to validated SQL, and receive AI-generated insights,
anomaly detection, and forecasts.

> **Status:** Phase 1 (foundation) complete. Features are being built in phases —
> see the roadmap below.

## Tech stack

| Layer    | Technology |
|----------|------------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui (Base UI), Lucide |
| Backend  | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database | PostgreSQL 16 — `public` schema (platform) + `data` schema (imported datasets) |
| AI       | Provider-abstracted LLM layer (Anthropic / OpenAI / deterministic demo mode) |
| Infra    | Docker, Docker Compose, GitHub Actions (CI lands in Phase 10) |

## Repository layout

```
frontend/    Next.js app (src/ layout, route groups: (auth) + (app))
backend/     FastAPI app — api / core / models / schemas / services
database/    init scripts (schemas, bi_reader role)
docker/      Dockerfiles (backend, frontend)
tests/e2e/   Playwright end-to-end tests (later phases)
docs/        Architecture, database, API, AI-system, deployment docs
```

## Quick start

### Docker (recommended)

```bash
cp .env.example .env        # dev defaults work out of the box
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000 · Swagger: http://localhost:8000/api/docs
- Postgres: localhost:5432 (user `bi_admin`)

Requires Docker Desktop with the WSL2 backend (`wsl --install` on Windows).

### Local development

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload                  # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                                    # http://localhost:3000
```

## Testing

```bash
cd backend
pytest            # unit/integration tests
```

## Environment variables

See [.env.example](.env.example). Highlights:

- `LLM_PROVIDER` — `none` (default, deterministic demo mode — no key needed),
  `anthropic`, or `openai`
- `SECRET_KEY` — generate a long random value for any non-local use
- `BI_READER_*` — read-only DB role used to execute AI-generated SQL

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Requirements, architecture, schema & API design | Done |
| 1 | Monorepo scaffold, Next.js shell, FastAPI, Postgres roles, Docker | Done |
| 2 | Authentication, RBAC, users | Next |
| 3 | Dataset upload, profiling, cleaning, versioning | Planned |
| 4 | Analytics dashboard, KPIs, charts | Planned |
| 5 | BI Copilot: NL→SQL, validation, chat | Planned |
| 6 | AI insights, anomaly detection, forecasting | Planned |
| 7 | Dashboard builder, saved queries, reports | Planned |
| 8 | Security hardening, audit logs, performance | Planned |
| 9 | Test suite (unit/integration/e2e) | Planned |
| 10 | CI/CD, docs, final polish | Planned |
