-- Scored layer consumed by the API: buzz intensity + PostGIS geometry.
--
--   intensity = w_articles * norm(num_articles)
--             + w_sources  * norm(num_sources)
--             + w_recency  * exp(-ln2 * age_hours / half_life)
--
-- norm(x) = least(1, ln(1+x) / ln(1+cap)) — saturating log, stable across
-- runs. Recency decays from the scoring run's clock; the API re-applies
-- decay relative to an arbitrary reference time for the time slider.

{{ config(
    post_hook=[
        "create index if not exists idx_events_scored_geom on {{ this }} using gist (geom)",
        "create index if not exists idx_events_scored_date_added on {{ this }} (date_added)",
        "create index if not exists idx_events_scored_root_code on {{ this }} (event_root_code)"
    ]
) }}

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
    st_setsrid(st_makepoint(lon, lat), 4326) as geom,
    source_url,
    page_title,
    {{ var('w_articles') }} * least(
        1.0,
        ln(1 + greatest(coalesce(num_articles, 0), 0))
        / ln(1 + {{ var('articles_cap') }})
    )
    + {{ var('w_sources') }} * least(
        1.0,
        ln(1 + greatest(coalesce(num_sources, 0), 0))
        / ln(1 + {{ var('sources_cap') }})
    )
    + {{ var('w_recency') }} * exp(
        -ln(2)
        * greatest(0, extract(epoch from (now() - date_added)) / 3600.0)
        / {{ var('half_life_hours') }}
    ) as intensity,
    ingested_at,
    now() as scored_at
from {{ ref('cleaned_events') }}
