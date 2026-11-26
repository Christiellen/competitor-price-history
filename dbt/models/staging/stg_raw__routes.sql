select
    route_id,
    origin_locality_id,
    destination_locality_id,
    distance_km
from {{ source('raw', 'routes') }}
