# Airflow orchestration (Phase 4)

The `gdelt_ingest` DAG replaces the Phase 1 cron job with a fault-tolerant,
re-runnable pipeline: **fetch → parse → validate → score → load**, every 15
minutes.

## Start / stop

```bash
docker compose -f infra/docker-compose.yml --profile airflow up -d
# UI: http://localhost:8080  (admin / admin — change for anything public)
docker compose -f infra/docker-compose.yml --profile airflow down
```

The stack reuses the project's Postgres container with a dedicated `airflow`
metadata database (created by `infra/postgres-init/02-airflow-db.sh` on fresh
volumes). The repo is mounted read-only at `/opt/newsbuzz`, so DAG tasks
import the same `ingestion/` code that cron ran — no duplicated logic.

## Why runs are idempotent and backfillable

Each 15-minute data interval maps deterministically to GDELT's timestamped
export files (`YYYYMMDDHHMMSS.export.CSV.zip`), instead of "whatever
lastupdate.txt says right now". GDELT keeps all historical files, and the
loader upserts on `GLOBALEVENTID`, so any interval can be re-run safely.

## Retries

Every task retries twice with exponential backoff (starting at 2 minutes) —
this directly covers the failure mode observed in Phase 1, where a cron run
died on a transient `data.gdeltproject.org` read timeout.

## Backfill

```bash
# Re-ingest a historical window (runs one DAG run per 15-min interval):
docker compose -f infra/docker-compose.yml exec airflow-scheduler \
  airflow dags backfill gdelt_ingest \
  --start-date 2026-07-03T00:00:00 --end-date 2026-07-03T06:00:00

# Re-run a single failed interval:
docker compose -f infra/docker-compose.yml exec airflow-scheduler \
  airflow tasks clear gdelt_ingest --start-date ... --end-date ... --yes
```

## Production note

Per the project spec, Airflow does not need to run 24/7 on the free-tier VM;
the Docker Compose profile is the demo/deployment vehicle, and `infra/cron/`
remains as the zero-overhead fallback scheduler.
