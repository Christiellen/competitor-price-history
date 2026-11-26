{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={'field': 'capture_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['route_id', 'departure_date', 'competitor_id'],
        on_schema_change='append_new_columns'
    )
}}

-- Grão: uma captura de tarifa = concorrente, rota, saída (data e hora),
-- classe de serviço e momento da captura.
--
-- Partição por data de CAPTURA: a carga diária toca só as datas capturadas.
-- Particionar por data da SAÍDA obrigaria cada carga a reescrever dezenas de
-- partições, porque o scraper consulta saídas de até 60 dias à frente.
-- O cluster por rota e data da saída compensa nas consultas por saída.

{%- set affected = get_affected_dates(ref('stg_raw__fare_captures'), 'capture_date', '_ingest_date') %}

with captures as (

    select *
    from {{ ref('stg_raw__fare_captures') }}
    where _ingest_date >= date '{{ var("start_date") }}'
    {%- if is_incremental() %}
      {%- if affected | length > 0 %}
      -- uma captura nunca é ingerida antes de acontecer
      and _ingest_date >= date '{{ affected | min }}'
      {%- endif %}
      and {{ date_in_list('capture_date', affected) }}
    {%- endif %}

),

deduplicated as (

    -- reenvio = mesma captura recebida de novo; vale a versão ingerida por último
    select *
    from captures
    qualify row_number() over (
        partition by competitor_id, origin_name, destination_name, departure_at,
                     service_class_label, captured_at
        order by ingested_at desc
    ) = 1

),

conformed as (

    select
        c.*,
        o.locality_id      as origin_locality_id,
        d.locality_id      as destination_locality_id,
        r.route_id,
        s.class_code
    from deduplicated as c
    left join {{ ref('stg_raw__locality_aliases') }} as o
        on o.competitor_id = c.competitor_id and o.raw_name = c.origin_name
    left join {{ ref('stg_raw__locality_aliases') }} as d
        on d.competitor_id = c.competitor_id and d.raw_name = c.destination_name
    left join {{ ref('stg_raw__routes') }} as r
        on r.origin_locality_id = o.locality_id
       and r.destination_locality_id = d.locality_id
    left join {{ ref('service_class_map') }} as s
        on s.raw_label = c.service_class_label

)

select
    {{ dbt_utils.generate_surrogate_key([
        'competitor_id', 'origin_name', 'destination_name',
        'departure_at', 'service_class_label', 'captured_at'
    ]) }}                                                   as capture_key,
    competitor_id,
    route_id,                                               -- nulo: rota fora da nossa malha
    origin_locality_id,
    destination_locality_id,
    class_code,                                             -- nulo: rótulo de classe desconhecido
    departure_at,
    departure_date,
    departure_time,
    captured_at,
    capture_date,
    date_diff(departure_date, capture_date, day)            as days_before_departure,
    {{ antecedence_band('date_diff(departure_date, capture_date, day)') }}       as antecedence_band,
    {{ antecedence_band_order('date_diff(departure_date, capture_date, day)') }} as antecedence_band_order,
    price,
    seats_available,
    is_sold_out,
    origin_name,
    destination_name,
    service_class_label,
    ingested_at
from conformed
