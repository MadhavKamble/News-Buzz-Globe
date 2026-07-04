-- Singular test: intensity must always land in [0, 1] given weights that sum to 1.
select global_event_id, intensity
from {{ ref('events_scored') }}
where intensity < 0 or intensity > 1
