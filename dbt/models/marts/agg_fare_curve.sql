{{
    config(
        materialized='table',
        partition_by={'field': 'departure_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['route_id', 'class_code']
    )
}}

-- Grão: rota x classe x data da saída x antecedência (dias antes da saída).
-- Compara a nossa tarifa com a do mercado NA MESMA ANTECEDÊNCIA: comparar a
-- nossa tarifa de hoje com a do concorrente para uma saída daqui a 30 dias
-- distorceria a leitura, porque o preço sobe conforme a saída se aproxima.
-- Particionada por data da SAÍDA: é assim que o painel e a análise de curva
-- filtram, e a tabela é reconstruída por inteiro.

with snapshots as (

    select s.*, c.is_own_company
    from {{ ref('fct_fare_snapshot_daily') }} as s
    join {{ ref('dim_competitor') }} as c using (competitor_id)

),

ours as (

    select
        route_id, class_code, departure_date, days_before_departure,
        count(*)                        as our_departures,
        countif(is_sold_out)            as our_sold_out_departures,
        avg(price)                      as our_avg_price
    from snapshots
    where is_own_company
    group by route_id, class_code, departure_date, days_before_departure

),

market as (

    select
        route_id, class_code, departure_date, days_before_departure,
        count(distinct competitor_id)   as competitors_count,
        count(*)                        as market_departures,
        countif(is_sold_out)            as market_sold_out_departures,
        min(price)                      as market_min_price,
        avg(price)                      as market_avg_price,
        max(price)                      as market_max_price,
        array_agg(if(is_sold_out, null, competitor_id) ignore nulls order by price, competitor_id limit 1)[safe_offset(0)]
                                        as cheapest_competitor_id
    from snapshots
    where not is_own_company
    group by route_id, class_code, departure_date, days_before_departure

),

joined as (

    select
        coalesce(o.route_id, m.route_id)                           as route_id,
        coalesce(o.class_code, m.class_code)                       as class_code,
        coalesce(o.departure_date, m.departure_date)               as departure_date,
        coalesce(o.days_before_departure, m.days_before_departure) as days_before_departure,
        o.our_departures, o.our_sold_out_departures, o.our_avg_price,
        m.competitors_count, m.market_departures, m.market_sold_out_departures,
        m.market_min_price, m.market_avg_price, m.market_max_price, m.cheapest_competitor_id
    from ours as o
    full outer join market as m
        using (route_id, class_code, departure_date, days_before_departure)

)

select
    route_id,
    class_code,
    departure_date,
    days_before_departure,
    date_sub(departure_date, interval days_before_departure day)          as capture_date,
    {{ antecedence_band('days_before_departure') }}                       as antecedence_band,
    {{ antecedence_band_order('days_before_departure') }}                 as antecedence_band_order,
    coalesce(our_departures, 0)                                           as our_departures,
    coalesce(our_sold_out_departures, 0)                                  as our_sold_out_departures,
    round(our_avg_price, 2)                                               as our_avg_price,
    coalesce(competitors_count, 0)                                        as competitors_count,
    coalesce(market_departures, 0)                                        as market_departures,
    coalesce(market_sold_out_departures, 0)                               as market_sold_out_departures,
    market_min_price,
    round(market_avg_price, 2)                                            as market_avg_price,
    market_max_price,
    cheapest_competitor_id,
    -- acima de 1: o mercado está mais caro que nós
    round(safe_divide(market_avg_price, our_avg_price), 4)                as price_index,
    case
        when our_avg_price is null then 'sem tarifa nossa'
        when market_min_price is null then 'sem tarifa do mercado'
        when our_avg_price < market_min_price then 'mais barato que todos'
        when our_avg_price > market_max_price then 'mais caro que todos'
        else 'dentro da faixa'
    end                                                                   as price_position
from joined
