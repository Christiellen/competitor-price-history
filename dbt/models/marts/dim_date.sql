-- Calendário contínuo da primeira captura à última saída. Usado em dois
-- papéis: data da captura e data da saída. Rótulos em português para o
-- Power BI (a FORMAT_DATE do BigQuery só gera nomes em inglês).

with bounds as (

    select min(capture_date) as first_day, max(departure_date) as last_day
    from {{ ref('fct_fare_snapshot_daily') }}

),

calendar as (

    select day as date_day
    from bounds, unnest(generate_date_array(first_day, last_day)) as day

)

select
    date_day,
    extract(year from date_day)                                       as year,
    extract(quarter from date_day)                                    as quarter,
    extract(month from date_day)                                      as month,
    ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'][
        offset(extract(month from date_day) - 1)]                     as month_short_pt,
    format_date('%Y-%m', date_day)                                    as year_month,
    extract(isoweek from date_day)                                    as iso_week,
    date_trunc(date_day, isoweek)                                     as week_start,
    -- 1 = segunda ... 7 = domingo
    mod(extract(dayofweek from date_day) + 5, 7) + 1                  as day_of_week,
    ['dom','seg','ter','qua','qui','sex','sáb'][
        offset(extract(dayofweek from date_day) - 1)]                 as day_name_pt,
    extract(dayofweek from date_day) in (1, 7)                        as is_weekend
from calendar
