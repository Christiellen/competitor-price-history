{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={'field': 'capture_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['route_id', 'departure_date', 'competitor_id'],
        on_schema_change='append_new_columns'
    )
}}

-- Grão: concorrente x rota x saída x classe x dia de captura.
-- Guarda a última captura de cada dia (o scraper consulta as saídas próximas
-- mais de uma vez por dia). Só entram capturas da nossa malha e de classes
-- conhecidas.

{%- set affected = get_affected_dates(ref('fct_fare_capture'), 'capture_date', 'date(ingested_at)') %}

with captures as (

    select *
    from {{ ref('fct_fare_capture') }}
    where route_id is not null
      and class_code is not null
    {%- if is_incremental() %}
      and {{ date_in_list('capture_date', affected) }}
    {%- endif %}

),

ranked as (

    select
        *,
        row_number() over day_window          as rn,
        count(*) over day_window_all           as captures_in_day,
        max(ingested_at) over day_window_all   as last_ingested_at
    from captures
    window
        day_window_all as (partition by competitor_id, route_id, departure_at, class_code, capture_date),
        day_window as (day_window_all order by captured_at desc, ingested_at desc)

)

select
    competitor_id,
    route_id,
    class_code,
    departure_at,
    departure_date,
    departure_time,
    capture_date,
    days_before_departure,
    antecedence_band,
    antecedence_band_order,
    price,
    seats_available,
    is_sold_out,
    captured_at                     as last_captured_at,
    captures_in_day,
    last_ingested_at                as ingested_at
from ranked
where rn = 1
