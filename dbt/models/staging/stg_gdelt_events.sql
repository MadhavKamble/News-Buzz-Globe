-- 1:1 typed staging layer over the raw landing table.
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
from {{ source('gdelt', 'raw_events') }}
