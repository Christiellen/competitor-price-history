select
    competitor_id,
    competitor_name,
    channel,
    is_own_company
from {{ ref('stg_raw__competitors') }}
