-- Cleaned/validated layer: declarative re-statement of the ingestion
-- validation rules, plus defensive dedupe (last write wins by recency).
--
-- Materialized as a VIEW: only events_scored reads it (during dbt builds),
-- so a table here would store every event a third time for no query-path
-- benefit. The API reads the indexed events_scored table.
{{ config(materialized='view') }}
with deduped as (
    select
        *,
        row_number() over (
            partition by global_event_id
            order by date_added desc, ingested_at desc
        ) as rn
    from {{ ref('stg_gdelt_events') }}
)

select
    global_event_id,
    event_date,
    date_added,
    actor1_name,
    actor2_name,
    event_code,
    event_root_code,
    quad_class,
    num_mentions,
    num_sources,
    num_articles,
    avg_tone,
    action_geo_full_name,
    action_geo_country_code,
    lat,
    lon,
    source_url,
    page_title,
    ingested_at
from deduped
where rn = 1
  -- plausible coordinates; (0,0) is GDELT's null-island junk geocode
  and lat is not null and lon is not null
  and lat between -90 and 90
  and lon between -180 and 180
  and not (lat = 0 and lon = 0)
  -- counts must be non-negative when present
  and coalesce(num_mentions, 0) >= 0
  and coalesce(num_sources, 0) >= 0
  and coalesce(num_articles, 0) >= 0
  -- well-formed CAMEO codes only
  and event_code is not null and event_code <> ''
  and event_root_code ~ '^(0[1-9]|1[0-9]|20)$'
