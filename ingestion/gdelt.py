"""GDELT 2.0 client: discover, download, and parse the latest 15-minute exports.

Two files per cycle:
- events export (``*.export.CSV.zip``): 61 tab-separated columns, no header.
- GKG (``*.gkg.csv.zip``): 27 tab-separated columns; its Extras XML carries
  ``<PAGE_TITLE>``, which we join to events by URL for human-readable labels.
"""

import html
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from common.logging_config import get_logger
from ingestion.config import GDELT_LASTUPDATE_URL

logger = get_logger("ingestion.gdelt")

REQUEST_TIMEOUT = 60

# GDELT 2.0 events export column positions (61 columns, tab-separated, no header).
COL_GLOBAL_EVENT_ID = 0
COL_SQLDATE = 1
COL_ACTOR1_NAME = 6
COL_ACTOR2_NAME = 16
COL_IS_ROOT_EVENT = 25
COL_EVENT_CODE = 26
COL_EVENT_BASE_CODE = 27
COL_EVENT_ROOT_CODE = 28
COL_QUAD_CLASS = 29
COL_GOLDSTEIN = 30
COL_NUM_MENTIONS = 31
COL_NUM_SOURCES = 32
COL_NUM_ARTICLES = 33
COL_AVG_TONE = 34
COL_ACTION_GEO_TYPE = 35 + 16  # 51
COL_ACTION_GEO_FULL_NAME = 52
COL_ACTION_GEO_COUNTRY = 53
COL_ACTION_GEO_LAT = 56
COL_ACTION_GEO_LON = 57
COL_DATE_ADDED = 59
COL_SOURCE_URL = 60
EVENT_EXPORT_NUM_COLS = 61

# GKG 2.1 column positions.
GKG_COL_DOCUMENT_IDENTIFIER = 4
GKG_COL_EXTRAS = 26
GKG_NUM_COLS = 27

_PAGE_TITLE_RE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.DOTALL)


@dataclass(frozen=True)
class ExportUrls:
    events_url: str
    gkg_url: str


@dataclass
class RawEvent:
    """One parsed GDELT event row, prior to validation/scoring."""

    global_event_id: int
    event_date: datetime
    date_added: datetime
    actor1_name: str | None
    actor2_name: str | None
    event_code: str
    event_root_code: str
    quad_class: int | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None
    avg_tone: float | None
    action_geo_full_name: str | None
    action_geo_country_code: str | None
    lat: float | None
    lon: float | None
    source_url: str | None
    page_title: str | None = None


class GdeltRowError(ValueError):
    """A row that cannot be parsed into a RawEvent. Carries a reason code."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def fetch_last_update(session: requests.Session | None = None) -> ExportUrls:
    """Read lastupdate.txt to find the newest export + GKG zip URLs."""
    sess = session or requests.Session()
    resp = sess.get(GDELT_LASTUPDATE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    events_url = gkg_url = None
    for line in resp.text.strip().splitlines():
        # Format: "<size> <md5> <url>"
        parts = line.split()
        if len(parts) != 3:
            continue
        url = parts[2]
        if url.endswith(".export.CSV.zip"):
            events_url = url
        elif url.endswith(".gkg.csv.zip"):
            gkg_url = url
    if not events_url or not gkg_url:
        raise RuntimeError(f"lastupdate.txt missing expected URLs: {resp.text!r}")
    return ExportUrls(events_url=events_url, gkg_url=gkg_url)


def download_zipped_csv(url: str, session: requests.Session | None = None) -> str:
    """Download a GDELT zip and return the inner CSV decoded as text.

    GDELT files are nominally UTF-8 but contain occasional mojibake from
    upstream scraping; undecodable bytes are replaced rather than dropped so
    one bad byte cannot kill a whole row (or file).
    """
    sess = session or requests.Session()
    resp = sess.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        inner = zf.namelist()[0]
        raw = zf.read(inner)
    return raw.decode("utf-8", errors="replace")


def _parse_timestamp(value: str, fmt: str) -> datetime:
    return datetime.strptime(value, fmt).replace(tzinfo=UTC)


def _opt_str(value: str) -> str | None:
    value = value.strip()
    return value or None


def _opt_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


def _opt_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    return float(value)


def parse_event_row(line: str) -> RawEvent:
    """Parse one tab-separated events-export line.

    Raises GdeltRowError with a machine-readable reason for malformed rows;
    the caller decides whether to drop and how to log.
    """
    fields = line.rstrip("\n").split("\t")
    if len(fields) != EVENT_EXPORT_NUM_COLS:
        raise GdeltRowError("bad_column_count", f"got {len(fields)}")
    try:
        global_event_id = int(fields[COL_GLOBAL_EVENT_ID])
    except ValueError as exc:
        raise GdeltRowError("bad_event_id", fields[COL_GLOBAL_EVENT_ID]) from exc
    try:
        event_date = _parse_timestamp(fields[COL_SQLDATE], "%Y%m%d")
        date_added = _parse_timestamp(fields[COL_DATE_ADDED], "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise GdeltRowError("bad_timestamp", str(exc)) from exc
    try:
        return RawEvent(
            global_event_id=global_event_id,
            event_date=event_date,
            date_added=date_added,
            actor1_name=_opt_str(fields[COL_ACTOR1_NAME]),
            actor2_name=_opt_str(fields[COL_ACTOR2_NAME]),
            event_code=fields[COL_EVENT_CODE].strip(),
            event_root_code=fields[COL_EVENT_ROOT_CODE].strip(),
            quad_class=_opt_int(fields[COL_QUAD_CLASS]),
            num_mentions=_opt_int(fields[COL_NUM_MENTIONS]),
            num_sources=_opt_int(fields[COL_NUM_SOURCES]),
            num_articles=_opt_int(fields[COL_NUM_ARTICLES]),
            avg_tone=_opt_float(fields[COL_AVG_TONE]),
            action_geo_full_name=_opt_str(fields[COL_ACTION_GEO_FULL_NAME]),
            action_geo_country_code=_opt_str(fields[COL_ACTION_GEO_COUNTRY]),
            lat=_opt_float(fields[COL_ACTION_GEO_LAT]),
            lon=_opt_float(fields[COL_ACTION_GEO_LON]),
            source_url=_opt_str(fields[COL_SOURCE_URL]),
        )
    except ValueError as exc:
        raise GdeltRowError("bad_numeric_field", str(exc)) from exc


def parse_events_csv(text: str) -> tuple[list[RawEvent], dict[str, int]]:
    """Parse a whole events export. Returns (events, drop_reason_counts)."""
    events: list[RawEvent] = []
    drops: dict[str, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            events.append(parse_event_row(line))
        except GdeltRowError as exc:
            drops[exc.reason] = drops.get(exc.reason, 0) + 1
    return events, drops


def parse_gkg_titles(text: str) -> dict[str, str]:
    """Map document URL -> page title from a GKG export.

    Rows without a PAGE_TITLE in Extras are simply absent from the map.
    """
    titles: dict[str, str] = {}
    for line in text.splitlines():
        fields = line.rstrip("\n").split("\t")
        if len(fields) != GKG_NUM_COLS:
            continue
        url = fields[GKG_COL_DOCUMENT_IDENTIFIER].strip()
        if not url:
            continue
        match = _PAGE_TITLE_RE.search(fields[GKG_COL_EXTRAS])
        if match:
            # Titles arrive HTML-escaped inside the Extras XML.
            title = html.unescape(match.group(1)).strip()
            if title:
                titles[url] = title
    return titles
