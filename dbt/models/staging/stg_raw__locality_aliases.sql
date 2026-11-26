-- mesma normalização aplicada aos nomes capturados
select
    competitor_id,
    upper(trim(raw_name)) as raw_name,
    locality_id
from {{ source('raw', 'locality_aliases') }}
