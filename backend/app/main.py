"""News Buzz Globe API."""

import re
from datetime import datetime
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from backend.app.auth import check_rate_limit, generate_token, get_current_user
from backend.app.cache import EventsCache, chat_cache_key, events_cache_key
from backend.app.queries import fetch_events, fetch_stories
from backend.app.schemas import (
    BoundingBox,
    ChatRequest,
    ChatResponse,
    FeatureCollection,
    StoryCollection,
    TokenRequest,
    TokenResponse,
)
from common.cameo import CAMEO_THEMES, codes_for_themes
from common.db import get_engine
from common.logging_config import get_logger

logger = get_logger("backend.api")

_ROOT_CODE_RE = re.compile(r"^(0[1-9]|1[0-9]|20)$")

app = FastAPI(
    title="News Buzz Globe API",
    description="Global news events from GDELT as GeoJSON, scored by buzz intensity.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # public data; no credentials involved
    allow_methods=["GET", "POST"],  # POST needed for /chat and /auth/token
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def shared_engine() -> Engine:
    return get_engine()


def engine_dep() -> Engine:
    return shared_engine()


@lru_cache(maxsize=1)
def shared_cache() -> EventsCache:
    return EventsCache()


def cache_dep() -> EventsCache:
    return shared_cache()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/themes")
def themes() -> dict:
    """CAMEO root-code theme groupings used by the category filter."""
    return CAMEO_THEMES


@app.get("/stats")
def stats(engine: Engine = Depends(engine_dep)) -> dict:
    """Pipeline liveness numbers for the UI stats bar."""
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import select

    from common.models import events_scored, ingestion_runs, story_clusters

    with engine.connect() as conn:
        total_events = conn.execute(
            select(sqlfunc.count()).select_from(events_scored)
        ).scalar()
        latest_story_run = conn.execute(
            select(sqlfunc.max(story_clusters.c.run_at))
        ).scalar()
        total_stories = conn.execute(
            select(sqlfunc.count())
            .select_from(story_clusters)
            .where(story_clusters.c.run_at == latest_story_run)
        ).scalar()
        last_run = conn.execute(
            select(ingestion_runs.c.run_at, ingestion_runs.c.rows_loaded)
            .order_by(ingestion_runs.c.run_at.desc())
            .limit(1)
        ).first()
    return {
        "total_events": total_events or 0,
        "total_stories": total_stories or 0,
        "last_ingestion_at": last_run.run_at.isoformat() if last_run else None,
        "last_ingestion_rows": last_run.rows_loaded if last_run else None,
    }


@app.get("/metrics/ingestion")
def ingestion_metrics(
    limit: int = Query(20, ge=1, le=500),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    """Recent ingestion runs: rows fetched/rejected/loaded and duration."""
    from sqlalchemy import select

    from common.models import ingestion_runs

    stmt = (
        select(ingestion_runs)
        .order_by(ingestion_runs.c.run_at.desc())
        .limit(limit)
    )
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


@app.get("/stories", response_model=StoryCollection)
def get_stories(
    limit: int = Query(500, ge=1, le=2000, description="Max stories, buzziest first."),
    engine: Engine = Depends(engine_dep),
) -> StoryCollection:
    """Deduplicated story hotspots from the latest clustering run (Phase 8)."""
    return fetch_stories(engine, limit=limit)


@app.get("/events", response_model=FeatureCollection)
def get_events(
    bbox: str | None = Query(
        None,
        description="Bounding box 'west,south,east,north' in degrees (EPSG:4326).",
        examples=["-10.5,35.0,30.0,60.0"],
    ),
    start: datetime | None = Query(None, description="Earliest date_added (inclusive)."),
    end: datetime | None = Query(None, description="Latest date_added (inclusive)."),
    category: list[str] | None = Query(
        None,
        description="CAMEO root codes ('01'-'20'); repeat the param for multiple.",
    ),
    theme: list[str] | None = Query(
        None,
        description="Theme keys from GET /themes; repeat for multiple. Merged with 'category'.",
    ),
    limit: int = Query(500, ge=1, le=5000, description="Max events, highest intensity first."),
    at: datetime | None = Query(
        None,
        description=(
            "Reference time for intensity: recency decay is computed relative to "
            "this instant (time-slider position). Defaults to as-of-ingestion scores."
        ),
    ),
    engine: Engine = Depends(engine_dep),
    cache: EventsCache = Depends(cache_dep),
    response: Response = None,  # type: ignore[assignment]
) -> FeatureCollection:
    parsed_bbox = None
    if bbox is not None:
        try:
            parsed_bbox = BoundingBox.from_query(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start must be <= end")
    if category:
        for code in category:
            if not _ROOT_CODE_RE.match(code):
                raise HTTPException(
                    status_code=422,
                    detail=f"invalid CAMEO root code {code!r}; expected '01'-'20'",
                )
    codes = list(category or [])
    if theme:
        try:
            codes.extend(codes_for_themes(theme))
        except KeyError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"unknown theme {exc.args[0]!r}; see GET /themes",
            ) from exc

    # Cache key covers every response-affecting param: bbox, time window,
    # reference time, category/theme filters, and limit.
    key = events_cache_key(bbox, start, end, at, category, theme, limit)
    cached = cache.get_json(key)
    if cached is not None:
        if response is not None:
            response.headers["X-Cache"] = "HIT"
        return FeatureCollection.model_validate(cached)

    result = fetch_events(
        engine,
        bbox=parsed_bbox,
        start=start,
        end=end,
        categories=sorted(set(codes)) or None,
        limit=limit,
        at=at,
    )
    cache.set_json(key, result.model_dump(mode="json"))
    if response is not None:
        response.headers["X-Cache"] = "MISS"
    return result


@app.post("/auth/token", response_model=TokenResponse)
def issue_token(body: TokenRequest) -> TokenResponse:
    """Demo JWT issuance: no password, just proves the JWT flow end-to-end."""
    return TokenResponse(access_token=generate_token(body.user_id))


@app.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user_id: str = Depends(get_current_user),
    cache: EventsCache = Depends(cache_dep),
) -> ChatResponse:
    """Ask a natural-language question, answered from indexed news stories."""
    from intelligence import rag

    check_rate_limit(user_id, cache.get_client())

    key = chat_cache_key(body.query)
    cached = cache.get_json(key)
    if cached is not None:
        return ChatResponse.model_validate({**cached, "cached": True})

    result = rag.answer(body.query)
    payload = {"answer": result.get("answer"), "sources": result.get("sources") or []}
    if payload["answer"] is not None:
        cache.set_json(key, payload, ttl=300)
    return ChatResponse.model_validate({**payload, "cached": False})
