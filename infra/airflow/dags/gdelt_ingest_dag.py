"""GDELT ingestion DAG: fetch → parse → validate → score → load.

Replaces the Phase 1 cron job. Each 15-minute data interval maps
deterministically to a timestamped GDELT export file, which makes runs
idempotent and enables true backfill (`airflow dags backfill`): GDELT keeps
every historical 15-minute file, and the loader upserts on GLOBALEVENTID.

Intermediate artifacts are handed between tasks as JSON files under
/opt/airflow/data/<cycle_ts>/ rather than XCom (payloads are a few MB).
"""

import json
import shutil
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

sys.path.insert(0, "/opt/newsbuzz")  # repo mount; provides ingestion/ + common/

DATA_DIR = Path("/opt/airflow/data")
GDELT_BASE = "http://data.gdeltproject.org/gdeltv2"


def _cycle_ts(data_interval_end: datetime) -> str:
    """GDELT publishes <ts>.export.CSV.zip at each quarter hour boundary."""
    floored = data_interval_end.replace(
        minute=(data_interval_end.minute // 15) * 15, second=0, microsecond=0
    )
    return floored.strftime("%Y%m%d%H%M%S")


def _read_events(path: Path):
    from ingestion.gdelt import RawEvent

    events = []
    with open(path) as fh:
        for line in fh:
            record = json.loads(line)
            record["event_date"] = datetime.fromisoformat(record["event_date"])
            record["date_added"] = datetime.fromisoformat(record["date_added"])
            events.append(RawEvent(**record))
    return events


def _write_events(path: Path, events) -> None:
    with open(path, "w") as fh:
        for event in events:
            record = asdict(event)
            record["event_date"] = event.event_date.isoformat()
            record["date_added"] = event.date_added.isoformat()
            fh.write(json.dumps(record) + "\n")


@dag(
    dag_id="gdelt_ingest",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 7, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
    },
    tags=["gdelt", "ingestion"],
)
def gdelt_ingest():
    @task
    def fetch(data_interval_end=None) -> str:
        """Download the events + GKG zips for this data interval."""
        from ingestion.gdelt import download_zipped_csv

        ts = _cycle_ts(data_interval_end)
        workdir = DATA_DIR / ts
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "events.csv").write_text(
            download_zipped_csv(f"{GDELT_BASE}/{ts}.export.CSV.zip")
        )
        (workdir / "gkg.csv").write_text(
            download_zipped_csv(f"{GDELT_BASE}/{ts}.gkg.csv.zip")
        )
        return str(workdir)

    @task
    def parse(workdir: str) -> str:
        """Parse raw CSVs into typed events + URL->title map."""
        from ingestion.gdelt import parse_events_csv, parse_gkg_titles

        wd = Path(workdir)
        events, drops = parse_events_csv((wd / "events.csv").read_text())
        titles = parse_gkg_titles((wd / "gkg.csv").read_text())
        _write_events(wd / "parsed.jsonl", events)
        (wd / "titles.json").write_text(json.dumps(titles))
        (wd / "parse_drops.json").write_text(json.dumps(drops))
        print(f"parsed={len(events)} drops={drops} titles={len(titles)}")
        return workdir

    @task
    def validate(workdir: str) -> str:
        """Apply data-quality rules; attach page titles to survivors."""
        from ingestion.validate import validate_events

        wd = Path(workdir)
        result = validate_events(_read_events(wd / "parsed.jsonl"))
        titles = json.loads((wd / "titles.json").read_text())
        for event in result.valid:
            if event.source_url and event.source_url in titles:
                event.page_title = titles[event.source_url]
        _write_events(wd / "valid.jsonl", result.valid)
        (wd / "validation_drops.json").write_text(json.dumps(result.drop_counts))
        print(f"valid={len(result.valid)} drops={result.drop_counts}")
        return workdir

    @task
    def load(workdir: str) -> None:
        """Upsert validated raw rows into Postgres, then emit run metrics."""
        from common.db import get_engine
        from ingestion.load import ensure_schema, event_to_row, upsert_events

        wd = Path(workdir)
        events = _read_events(wd / "valid.jsonl")
        engine = get_engine()
        ensure_schema(engine)
        loaded = upsert_events(engine, [event_to_row(e) for e in events])
        metrics = {
            "cycle": wd.name,
            "rows_loaded": loaded,
            "parse_drops": json.loads((wd / "parse_drops.json").read_text()),
            "validation_drops": json.loads((wd / "validation_drops.json").read_text()),
        }
        print(f"metrics={json.dumps(metrics)}")
        shutil.rmtree(wd, ignore_errors=True)  # workdir is scratch, not an archive

    # Since Phase 7 scoring lives in dbt: staging -> cleaned -> scored,
    # including dbt data tests (schema + intensity-range assertions).
    transform = BashOperator(
        task_id="transform",
        bash_command=(
            "dbt build --project-dir /opt/newsbuzz/dbt "
            "--profiles-dir /opt/newsbuzz/dbt/profiles "
            "--target-path /tmp/dbt-target --log-path /tmp/dbt-logs"
        ),
    )

    load(validate(parse(fetch()))) >> transform


gdelt_ingest()
