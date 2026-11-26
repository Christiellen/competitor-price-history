-- Dois períodos da mesma saída não podem se sobrepor.
with ordered as (

    select
        *,
        lead(valid_from) over (
            partition by competitor_id, route_id, class_code, departure_at
            order by valid_from
        ) as next_valid_from
    from {{ ref('fct_fare_interval') }}

)

select *
from ordered
where next_valid_from is not null
  and next_valid_from <= last_seen_date
