select distinct
    class_code,
    class_name,
    class_rank
from {{ ref('service_class_map') }}
