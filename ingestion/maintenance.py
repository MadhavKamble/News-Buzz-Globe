"""Weekly retention/rollup maintenance (Phase 10-adjacent storage control).

Policy:
- Raw event rows are kept for a 90-day rolling window.
- Any raw_events partition that lies entirely beyond the window is first
  downsampled into events_rollup_daily — daily aggregates per 2-degree
  location grid cell per CAMEO root code (the same grid-cell idea as the
  frontend zoom clustering, at its finest granularity) — and then dropped.
  History survives at coarse grain; storage stops growing without bound.

Idempotent: rollup inserts use ON CONFLICT DO NOTHING keyed on
(day, cell_lat, cell_lon, event_root_code), so a re-run after a partial
failure never double-counts, and partitions are only dropped after their
rollup insert commits.

Run weekly via cron (see infra/cron/maintenance.sh).
"""

import argparse
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from common.db import get_engine
from common.logging_config import get_logger
from ingestion.partitions import list_partitions

logger = get_logger("ingestion.maintenance")

RETENTION_DAYS = 90
CELL_DEG = 2  # finest grid used by the UI zoom clustering

ROLLUP_DDL = """
CREATE TABLE IF NOT EXISTS events_rollup_daily (
    day date NOT NULL,
    cell_lat integer NOT NULL,
    cell_lon integer NOT NULL,
    event_root_code text NOT NULL,
    rep_lat double precision NOT NULL,
    rep_lon double precision NOT NULL,
    event_count integer NOT NULL,
    total_articles bigint,
    total_sources bigint,
    avg_tone double precision,
    rolled_up_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, cell_lat, cell_lon, event_root_code)
)
"""

ROLLUP_INSERT = f"""
INSERT INTO events_rollup_daily
    (day, cell_lat, cell_lon, event_root_code, rep_lat, rep_lon,
     event_count, total_articles, total_sources, avg_tone)
SELECT
    date_trunc('day', date_added)::date AS day,
    floor(lat / {CELL_DEG})::int AS cell_lat,
    floor(lon / {CELL_DEG})::int AS cell_lon,
    event_root_code,
    avg(lat) AS rep_lat,
    avg(lon) AS rep_lon,
    count(*) AS event_count,
    sum(num_articles) AS total_articles,
    sum(num_sources) AS total_sources,
    avg(avg_tone) AS avg_tone
FROM {{partition}}
GROUP BY 1, 2, 3, 4
ON CONFLICT (day, cell_lat, cell_lon, event_root_code) DO NOTHING
"""


def run_once(database_url: str | None = None, as_of: datetime | None = None) -> dict:
    started = time.monotonic()
    engine = get_engine(database_url)
    now = as_of or datetime.now(UTC)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    with engine.begin() as conn:
        conn.execute(text(ROLLUP_DDL))

    dropped = []
    rollup_rows = 0
    for part in list_partitions(engine):
        if part["upper"] > cutoff:
            continue  # partition still (partially) inside the retention window
        with engine.begin() as conn:
            result = conn.execute(text(ROLLUP_INSERT.format(partition=part["name"])))
            rollup_rows += result.rowcount
            conn.execute(text(f"DROP TABLE {part['name']}"))
        dropped.append(part["name"])
        logger.info(
            "partition rolled up and dropped",
            extra={"partition": part["name"], "rollup_rows": result.rowcount},
        )

    metrics = {
        "cutoff": cutoff.isoformat(),
        "partitions_dropped": dropped,
        "rollup_rows_written": rollup_rows,
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("maintenance run complete", extra=metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="News Buzz Globe retention/rollup job")
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--as-of", default=None, help="override 'now' (ISO timestamp) for testing"
    )
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    run_once(args.database_url, as_of)


if __name__ == "__main__":
    main()
