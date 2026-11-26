-- Marca as mudanças de tarifa de cada saída ao longo das capturas e numera os
-- períodos de mesma tarifa (gaps and islands).
-- "Esgotado" é um estado próprio: a saída que esgota e depois volta a ter
-- assento à venda gera três períodos.

with snapshots as (

    select
        competitor_id,
        route_id,
        class_code,
        departure_at,
        capture_date,
        days_before_departure,
        price,
        is_sold_out,
        if(is_sold_out, 'ESGOTADO', cast(price as string)) as fare_state
    from {{ ref('fct_fare_snapshot_daily') }}

),

with_previous as (

    select
        *,
        lag(fare_state) over w   as prev_fare_state,
        lag(price) over w        as prev_price
    from snapshots
    window w as (partition by competitor_id, route_id, class_code, departure_at order by capture_date)

),

flagged as (

    select
        *,
        prev_fare_state is null or fare_state != prev_fare_state as is_change
    from with_previous

)

select
    *,
    safe_divide(price - prev_price, prev_price) as pct_change,
    sum(if(is_change, 1, 0)) over (
        partition by competitor_id, route_id, class_code, departure_at
        order by capture_date
        rows between unbounded preceding and current row
    )                                           as fare_period
from flagged
