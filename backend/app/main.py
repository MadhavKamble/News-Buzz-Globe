"""News Buzz Globe API."""

import re
from datetime import datetime
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from backend.app.queries import fetch_events
from backend.app.schemas import BoundingBox, FeatureCollection
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
    allow_origins=["*"],  # public read-only data; no credentials involved
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def shared_engine() -> Engine:
    return get_engine()


def engine_dep() -> Engine:
    return shared_engine()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
    limit: int = Query(500, ge=1, le=5000, description="Max events, highest intensity first."),
    engine: Engine = Depends(engine_dep),
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
    return fetch_events(
        engine,
        bbox=parsed_bbox,
        start=start,
        end=end,
        categories=category,
        limit=limit,
    )
