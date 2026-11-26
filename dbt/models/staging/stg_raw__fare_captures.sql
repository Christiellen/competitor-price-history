-- Padroniza tipos e textos. Preço vira NUMERIC: dinheiro não deve ser FLOAT.
-- capture_date é a data LOCAL da captura: captured_at está em UTC, e uma
-- captura às 22h em São Paulo já é o dia seguinte em UTC.
-- A tabela de origem exige filtro em _ingest_date: quem consome esta view
-- sempre filtra por ela.
select
    competitor_id,
    upper(trim(origin_name))                                  as origin_name,
    upper(trim(destination_name))                             as destination_name,
    departure_at,
    date(departure_at)                                        as departure_date,
    time(departure_at)                                        as departure_time,
    upper(trim(service_class_label))                          as service_class_label,
    cast(round(price, 2) as numeric)                          as price,
    seats_available,
    coalesce(is_sold_out, price is null)                      as is_sold_out,
    captured_at,
    date(captured_at, '{{ var("local_timezone") }}')          as capture_date,
    ingested_at,
    _ingest_date,
    source_file
from {{ source('raw', 'price_captures') }}
