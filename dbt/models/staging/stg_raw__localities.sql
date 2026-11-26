select
    locality_id,
    city,
    state,
    ibge_code
from {{ source('raw', 'localities') }}
