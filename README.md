# News Buzz Globe

Global news events, visualized as buzz-intensity hotspots on an interactive 3D globe — powered entirely by [GDELT](https://www.gdeltproject.org/), on $0/month infrastructure.

> **Status: under construction.** This README is completed in Phase 11 with the
> architecture diagram, live link, demo GIF, and engineering-decisions writeup.

## Quick start (dev)

```bash
# 1. Database (Postgres + PostGIS)
docker compose -f infra/docker-compose.yml up -d

# 2. Python env
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 3. Lint + tests
.venv/bin/ruff check . && .venv/bin/pytest

# 4. Backend API (http://localhost:8000/docs)
.venv/bin/uvicorn backend.app.main:app --port 8000

# 5. Frontend (http://localhost:5173)
cd frontend && npm install && npm run dev

# 6. Orchestration via Airflow (http://localhost:8080, admin/admin) — Phase 4+
docker compose -f infra/docker-compose.yml --profile airflow up -d
```

Ingestion scheduling: the `gdelt_ingest` Airflow DAG runs every 15 minutes
(fetch → parse → validate → score → load) with retries and backfill
(`airflow dags backfill`). A plain-cron fallback lives in `infra/cron/` for
environments where running Airflow isn't worth it.

## Repo layout

| Directory | Purpose |
|---|---|
| `ingestion/` | GDELT fetch → parse → validate → score → load pipeline |
| `backend/` | FastAPI GeoJSON API |
| `frontend/` | React + react-globe.gl app |
| `infra/` | Docker Compose, DB init, cron/Airflow assets |
| `tests/` | pytest suite |
| `common/` | Shared structured-logging config |
