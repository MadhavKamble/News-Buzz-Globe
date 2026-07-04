"""End-to-end ingestion run: fetch → parse → validate → load (raw).

Invoked by cron every 15 minutes (Phase 1); the same steps run as Airflow
tasks since Phase 4. Since Phase 7, scoring/geometry live in the dbt project
(staging → cleaned → scored) — run `dbt build` after loading, which the cron
wrapper and the Airflow DAG both do. Emits structured metrics per run: rows
fetched, rows rejected (by reason), rows loaded, and duration.
"""

import argparse
import time
from datetime import UTC, datetime

import requests

from common.db import get_engine
from common.logging_config import get_logger
from common.models import ingestion_runs
from ingestion.gdelt import (
    download_zipped_csv,
    fetch_last_update,
    parse_events_csv,
    parse_gkg_titles,
)
from ingestion.load import ensure_schema, event_to_row, upsert_events
from ingestion.validate import validate_events

logger = get_logger("ingestion.pipeline")


def record_metrics(engine, metrics: dict, source: str) -> None:
    """Persist one ingestion_runs row (Phase 10). Shared with the Airflow DAG."""
    with engine.begin() as conn:
        conn.execute(
            ingestion_runs.insert(),
            {
                "run_at": datetime.now(UTC),
                "source": source,
                "rows_fetched": metrics["rows_fetched"],
                "rows_parsed": metrics["rows_parsed"],
                "rows_rejected": metrics["rows_rejected"],
                "rows_loaded": metrics["rows_loaded"],
                "titles_matched": metrics.get("titles_matched"),
                "parse_drops": metrics.get("parse_drops", {}),
                "validation_drops": metrics.get("validation_drops", {}),
                "duration_seconds": metrics["duration_seconds"],
            },
        )


def run_once(database_url: str | None = None, source: str = "cron") -> dict:
    """One full ingestion cycle. Returns the metrics dict it also logs."""
    started = time.monotonic()
    session = requests.Session()

    urls = fetch_last_update(session)
    logger.info("fetching exports", extra={"events_url": urls.events_url})
    events_csv = download_zipped_csv(urls.events_url, session)
    gkg_csv = download_zipped_csv(urls.gkg_url, session)

    parsed, parse_drops = parse_events_csv(events_csv)
    titles = parse_gkg_titles(gkg_csv)

    result = validate_events(parsed)
    for event in result.valid:
        if event.source_url and event.source_url in titles:
            event.page_title = titles[event.source_url]

    rows = [event_to_row(event) for event in result.valid]

    engine = get_engine(database_url)
    ensure_schema(engine)
    loaded = upsert_events(engine, rows)

    metrics = {
        "rows_fetched": len(parsed) + sum(parse_drops.values()),
        "rows_parsed": len(parsed),
        "parse_drops": parse_drops,
        "validation_drops": result.drop_counts,
        "rows_rejected": sum(parse_drops.values()) + sum(result.drop_counts.values()),
        "rows_loaded": loaded,
        "titles_matched": sum(1 for e in result.valid if e.page_title),
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    record_metrics(engine, metrics, source)
    logger.info("ingestion run complete", extra=metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="News Buzz Globe GDELT ingestion")
    parser.add_argument("--database-url", default=None, help="override DATABASE_URL")
    args = parser.parse_args()
    run_once(args.database_url)


if __name__ == "__main__":
    main()
