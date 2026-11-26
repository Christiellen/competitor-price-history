{{
    config(
        materialized='table',
        partition_by={'field': 'departure_date', 'data_type': 'date', 'granularity': 'month'},
        cluster_by=['route_id', 'competitor_id']
    )
}}

-- Grão: um período de mesma tarifa (ou de esgotamento) de uma saída.
-- Responde "quando e de quanto o concorrente mudou a tarifa desta saída"
-- lendo uma fração das linhas da fato diária.
-- Reconstruída por inteiro a cada execução. Com o volume real, o próximo passo
-- seria torná-la incremental por data de saída afetada.

with periods as (

    select
        competitor_id,
        route_id,
        class_code,
        departure_at,
        fare_period,
        any_value(price)                    as price,
        any_value(is_sold_out)              as is_sold_out,
        min(capture_date)                   as valid_from,
        max(capture_date)                   as last_seen_date,
        max(days_before_departure)          as days_before_departure_start,
        min(days_before_departure)          as days_before_departure_end,
        count(*)                            as days_captured
    from {{ ref('int_fare_changes') }}
    group by competitor_id, route_id, class_code, departure_at, fare_period

)

select
    {{ dbt_utils.generate_surrogate_key(['competitor_id', 'route_id', 'class_code', 'departure_at', 'valid_from']) }}
                                                             as fare_interval_key,
    competitor_id,
    route_id,
    class_code,
    departure_at,
    date(departure_at)                                       as departure_date,
    price,
    is_sold_out,
    valid_from,
    last_seen_date,
    -- o período vale até a véspera do próximo; o último fica em aberto
    date_sub(lead(valid_from) over w, interval 1 day)        as valid_to,
    lead(valid_from) over w is null                          as is_last_period,
    days_before_departure_start,
    days_before_departure_end,
    lag(price) over w                                        as previous_price,
    safe_divide(price - lag(price) over w, lag(price) over w) as pct_change_from_previous,
    days_captured
from periods
window w as (partition by competitor_id, route_id, class_code, departure_at order by valid_from)
