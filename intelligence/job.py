"""Story clustering job: merge duplicate events into labeled story clusters.

Runs after each ingest+dbt cycle (see infra/cron/ingest.sh):
1. Pull recent titled events from events_scored.
2. Embed titles locally (sentence-transformers) and cluster by cosine
   similarity (union-find).
3. Label each cluster: Ollama one-liner for multi-member clusters (top-K by
   size), best member title otherwise or when Ollama is down.
4. Write one row per cluster to story_clusters; the API serves the latest run.

The marker location is the highest-buzz member's location (not the centroid):
the same global story reported from several places should sit on the place
where coverage is strongest, not in the middle of the ocean.
"""

import argparse
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from common.db import get_engine
from common.logging_config import get_logger
from common.models import events_scored, stories_metadata, story_clusters
from intelligence.cluster import cluster_embeddings, embed_titles
from intelligence.summarize import summarize_titles

logger = get_logger("intelligence.job")

WINDOW_HOURS = 6
SIMILARITY_THRESHOLD = 0.6
MAX_LLM_SUMMARIES = 25  # per run; larger clusters first
RETENTION_HOURS = 72


def _member_weight(row) -> tuple:
    return (row.num_articles or 0, row.intensity)


def compute_trend(members: list, run_at: datetime) -> tuple[str, int, int]:
    """Growing or dying vs. 1 hour ago.

    Compares article volume that arrived in the last hour against the hour
    before it (GDELT re-emits events as coverage grows, so date_added buckets
    approximate coverage arrival). Returns (trend, last_hour, prev_hour).
    """
    one_hour_ago = run_at - timedelta(hours=1)
    two_hours_ago = run_at - timedelta(hours=2)
    last_hour = sum(
        m.num_articles or 0 for m in members if m.date_added >= one_hour_ago
    )
    prev_hour = sum(
        m.num_articles or 0
        for m in members
        if two_hours_ago <= m.date_added < one_hour_ago
    )
    if last_hour > prev_hour * 1.2:
        trend = "rising"
    elif last_hour < prev_hour * 0.8:
        trend = "falling"
    else:
        trend = "steady"
    return trend, last_hour, prev_hour


def build_cluster_row(members: list, run_at: datetime, summary: str) -> dict:
    rep = max(members, key=_member_weight)
    tones = [m.avg_tone for m in members if m.avg_tone is not None]
    urls = list(
        dict.fromkeys(m.source_url for m in members if m.source_url)
    )[:5]
    trend, last_hour, prev_hour = compute_trend(members, run_at)
    return {
        "trend": trend,
        "articles_last_hour": last_hour,
        "articles_prev_hour": prev_hour,
        "run_at": run_at,
        "summary": summary,
        "lat": rep.lat,
        "lon": rep.lon,
        "member_count": len(members),
        "total_articles": sum(m.num_articles or 0 for m in members),
        "total_sources": sum(m.num_sources or 0 for m in members),
        "intensity": max(m.intensity for m in members),
        "avg_tone": sum(tones) / len(tones) if tones else None,
        "event_ids": [m.global_event_id for m in members],
        "source_urls": urls,
        "location": rep.action_geo_full_name,
        "country_code": rep.action_geo_country_code,
        "earliest": min(m.date_added for m in members),
        "latest": max(m.date_added for m in members),
    }


def run_once(database_url: str | None = None, window_hours: int = WINDOW_HOURS) -> dict:
    started = time.monotonic()
    engine = get_engine(database_url)
    stories_metadata.create_all(engine)
    run_at = datetime.now(UTC)
    cutoff = run_at - timedelta(hours=window_hours)

    with engine.connect() as conn:
        rows = conn.execute(
            select(events_scored)
            .where(events_scored.c.date_added >= cutoff)
            .where(events_scored.c.page_title.isnot(None))
        ).fetchall()

    if not rows:
        logger.info("no titled events in window; nothing to cluster")
        return {"clusters": 0, "events": 0}

    embeddings = embed_titles([r.page_title for r in rows])
    clusters = cluster_embeddings(embeddings, SIMILARITY_THRESHOLD)

    cluster_rows = []
    llm_used = 0
    for indices in clusters:
        members = [rows[i] for i in indices]
        titles = [m.page_title for m in members]
        summary = None
        if len(members) >= 2 and llm_used < MAX_LLM_SUMMARIES:
            summary = summarize_titles(titles)
            if summary:
                llm_used += 1
        if not summary:
            summary = max(members, key=_member_weight).page_title
        cluster_rows.append(build_cluster_row(members, run_at, summary))

    with engine.begin() as conn:
        conn.execute(
            delete(story_clusters).where(
                story_clusters.c.run_at < run_at - timedelta(hours=RETENTION_HOURS)
            )
        )
        conn.execute(story_clusters.insert(), cluster_rows)

    metrics = {
        "events": len(rows),
        "clusters": len(cluster_rows),
        "multi_member_clusters": sum(1 for c in cluster_rows if c["member_count"] > 1),
        "llm_summaries": llm_used,
        "dedup_ratio": round(len(cluster_rows) / len(rows), 3),
        "duration_seconds": round(time.monotonic() - started, 2),
    }
    logger.info("story clustering complete", extra=metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="News Buzz Globe story clustering")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--window-hours", type=int, default=WINDOW_HOURS)
    args = parser.parse_args()
    run_once(args.database_url, args.window_hours)


if __name__ == "__main__":
    main()
