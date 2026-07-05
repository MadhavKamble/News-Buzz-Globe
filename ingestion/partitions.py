"""Monthly range partitioning for the raw_events landing table.

raw_events is partitioned by RANGE (date_added), one partition per calendar
month (raw_events_yYYYYmMM). Recent-window queries prune to the relevant
partition(s), and the retention job drops whole months in O(1) instead of
DELETE-ing rows.

Note the primary key is (global_event_id, date_added) — Postgres requires the
partition key inside unique constraints. GDELT occasionally re-emits an event
under a fresher date_added; those land as separate raw rows, and the dbt
cleaned layer already dedupes by global_event_id (latest date_added wins).
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from common.logging_config import get_logger

logger = get_logger("ingestion.partitions")

RAW_EVENTS_DDL = """
CREATE TABLE raw_events (
    global_event_id bigint NOT NULL,
    event_date timestamptz NOT NULL,
    date_added timestamptz NOT NULL,
    actor1_name text,
    actor2_name text,
    event_code text NOT NULL,
    event_root_code text NOT NULL,
    quad_class smallint,
    num_mentions integer,
    num_sources integer,
    num_articles integer,
    avg_tone double precision,
    action_geo_full_name text,
    action_geo_country_code text,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    source_url text,
    page_title text,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (global_event_id, date_added)
) PARTITION BY RANGE (date_added)
"""


def month_start(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(dt: datetime) -> datetime:
    start = month_start(dt)
    return start.replace(year=start.year + 1, month=1) if start.month == 12 \
        else start.replace(month=start.month + 1)


def partition_name(dt: datetime) -> str:
    start = month_start(dt)
    return f"raw_events_y{start.year}m{start.month:02d}"


def is_partitioned(engine: Engine) -> bool | None:
    """True/False for existing raw_events; None if the table doesn't exist."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'raw_events'"
            )
        ).first()
    if row is None:
        return None
    return row.relkind == "p"


def ensure_partition_for(engine: Engine, dt: datetime) -> None:
    name = partition_name(dt)
    start = month_start(dt)
    end = next_month(dt)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF raw_events "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )


def ensure_raw_events(engine: Engine) -> None:
    """Create the partitioned table, migrating a legacy plain table in place."""
    state = is_partitioned(engine)
    if state is True:
        return
    if state is None:
        with engine.begin() as conn:
            conn.execute(text(RAW_EVENTS_DDL))
            conn.execute(
                text("CREATE INDEX idx_raw_events_date_added ON raw_events (date_added)")
            )
        logger.info("created partitioned raw_events")
        return

    # Legacy non-partitioned table: rename, recreate partitioned, copy, drop.
    with engine.begin() as conn:
        bounds = conn.execute(
            text("SELECT min(date_added) AS lo, max(date_added) AS hi FROM raw_events")
        ).first()
        conn.execute(text("ALTER TABLE raw_events RENAME TO raw_events_migrating"))
        conn.execute(text(RAW_EVENTS_DDL))
        conn.execute(
            text("CREATE INDEX idx_raw_events_date_added ON raw_events (date_added)")
        )
        if bounds.lo is not None:
            cursor = month_start(bounds.lo)
            while cursor <= bounds.hi:
                name = partition_name(cursor)
                conn.execute(
                    text(
                        f"CREATE TABLE {name} PARTITION OF raw_events "
                        f"FOR VALUES FROM ('{cursor.isoformat()}') "
                        f"TO ('{next_month(cursor).isoformat()}')"
                    )
                )
                cursor = next_month(cursor)
            conn.execute(
                text(
                    "INSERT INTO raw_events SELECT * FROM raw_events_migrating "
                    "ON CONFLICT DO NOTHING"
                )
            )
        # CASCADE: dbt's stg view follows the rename; dbt recreates it on
        # the next build, so dropping it here is safe.
        conn.execute(text("DROP TABLE raw_events_migrating CASCADE"))
    logger.info("migrated raw_events to monthly partitions")


def list_partitions(engine: Engine) -> list[dict]:
    """[{name, lower, upper}] for raw_events partitions, oldest first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname AS name, "
                "pg_get_expr(c.relpartbound, c.oid) AS bound "
                "FROM pg_inherits i "
                "JOIN pg_class c ON c.oid = i.inhrelid "
                "JOIN pg_class p ON p.oid = i.inhparent "
                "WHERE p.relname = 'raw_events' ORDER BY c.relname"
            )
        ).fetchall()
    partitions = []
    for row in rows:
        # bound looks like: FOR VALUES FROM ('2026-07-01 ...') TO ('2026-08-01 ...')
        parts = row.bound.split("'")
        partitions.append(
            {
                "name": row.name,
                "lower": datetime.fromisoformat(parts[1]),
                "upper": datetime.fromisoformat(parts[3]),
            }
        )
    return partitions
