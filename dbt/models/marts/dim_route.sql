select
    r.route_id,
    o.city                                                    as origin_city,
    o.state                                                   as origin_state,
    d.city                                                    as destination_city,
    d.state                                                   as destination_state,
    concat(o.city, '/', o.state, ' - ', d.city, '/', d.state) as route_name,
    -- mesmo par nos dois sentidos, para agrupar ida e volta
    concat(least(o.city, d.city), ' - ', greatest(o.city, d.city)) as city_pair,
    r.distance_km,
    o.ibge_code                                               as origin_ibge_code,
    d.ibge_code                                               as destination_ibge_code
from {{ ref('stg_raw__routes') }} as r
join {{ ref('stg_raw__localities') }} as o on o.locality_id = r.origin_locality_id
join {{ ref('stg_raw__localities') }} as d on d.locality_id = r.destination_locality_id
