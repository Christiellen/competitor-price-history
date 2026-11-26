-- Alerta (não bloqueia): tarifa de uma saída que muda mais que o limite de um
-- dia para o outro costuma ser erro de captura, mas pode ser feriado ou
-- reação a concorrente. Deve ser investigada antes de parar a carga.
{{ config(severity='warn') }}

select
    competitor_id,
    route_id,
    class_code,
    departure_at,
    capture_date,
    prev_price,
    price,
    pct_change
from {{ ref('int_fare_changes') }}
where abs(pct_change) > {{ var('price_jump_threshold') }}
