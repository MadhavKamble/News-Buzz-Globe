"""Data-quality validation for parsed GDELT events.

Rules (each drop is counted by reason and logged by the pipeline):
- coordinates must exist and be a plausible lat/lon (not null, not (0, 0),
  which GDELT uses as a junk geocode, and within world bounds)
- counts must be non-negative when present
- duplicate GLOBALEVENTIDs within a batch are collapsed (last wins — GDELT
  re-emits an event when its mention counts grow, so latest is freshest);
  duplicates across batches are handled by the loader's upsert.
"""

from dataclasses import dataclass, field

from ingestion.gdelt import RawEvent


@dataclass
class ValidationResult:
    valid: list[RawEvent] = field(default_factory=list)
    drop_counts: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.drop_counts[reason] = self.drop_counts.get(reason, 0) + 1


def _has_valid_coordinates(event: RawEvent) -> bool:
    if event.lat is None or event.lon is None:
        return False
    if not (-90.0 <= event.lat <= 90.0 and -180.0 <= event.lon <= 180.0):
        return False
    # (0, 0) is GDELT's null-island junk geocode for unresolvable locations.
    if event.lat == 0.0 and event.lon == 0.0:
        return False
    return True


def _has_valid_counts(event: RawEvent) -> bool:
    for count in (event.num_mentions, event.num_sources, event.num_articles):
        if count is not None and count < 0:
            return False
    return True


def validate_events(events: list[RawEvent]) -> ValidationResult:
    result = ValidationResult()
    seen: dict[int, int] = {}  # global_event_id -> index in result.valid
    for event in events:
        if not _has_valid_coordinates(event):
            result.drop("invalid_coordinates")
            continue
        if not _has_valid_counts(event):
            result.drop("negative_counts")
            continue
        if not event.event_code:
            result.drop("missing_event_code")
            continue
        existing = seen.get(event.global_event_id)
        if existing is not None:
            result.valid[existing] = event
            result.drop("duplicate_event_id_in_batch")
            continue
        seen[event.global_event_id] = len(result.valid)
        result.valid.append(event)
    return result
