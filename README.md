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
```

## Repo layout

| Directory | Purpose |
|---|---|
| `ingestion/` | GDELT fetch → parse → validate → score → load pipeline |
| `backend/` | FastAPI GeoJSON API |
| `frontend/` | React + react-globe.gl app |
| `infra/` | Docker Compose, DB init, cron/Airflow assets |
| `tests/` | pytest suite |
| `common/` | Shared structured-logging config |
