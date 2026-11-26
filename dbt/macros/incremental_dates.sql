{#
  Carga incremental por "datas afetadas".

  As fatos são particionadas por data de captura e usam a estratégia
  insert_overwrite: cada partição tocada é reescrita por inteiro. Por isso a
  nova carga precisa trazer TODAS as linhas das datas de captura afetadas,
  não só as linhas novas.

  1. Ponto de corte = maior data de ingestão já processada em {{ this }}
     menos `lookback_days`.
  2. Datas afetadas = datas de captura que receberam alguma linha ingerida
     a partir do ponto de corte (inclui chegadas atrasadas e reenvios).
  3. O modelo reprocessa só essas datas.

  As duas consultas rodam antes do modelo (run_query) e o resultado entra no
  SQL como literal. Filtros com valores constantes garantem o partition
  pruning do BigQuery, o que não acontece com uma subquery.
#}

{% macro get_affected_dates(source_relation, date_column, ingest_column, ingested_at_column='ingested_at') %}
  {%- if not execute or not is_incremental() -%}
    {{ return([]) }}
  {%- endif -%}

  {%- set cutoff_sql -%}
    select date_sub(max(date({{ ingested_at_column }})), interval {{ var('lookback_days') }} day)
    from {{ this }}
  {%- endset -%}
  {%- set cutoff = run_query(cutoff_sql).columns[0].values()[0] -%}
  {%- if cutoff is none -%}
    {%- set cutoff = var('start_date') -%}
  {%- endif -%}

  {%- set dates_sql -%}
    select distinct {{ date_column }}
    from {{ source_relation }}
    where {{ ingest_column }} >= date '{{ cutoff }}'
    order by 1
  {%- endset -%}
  {%- set dates = run_query(dates_sql).columns[0].values() | map('string') | list -%}
  {{ log(this.identifier ~ ': ' ~ (dates | length) ~ ' datas afetadas desde ' ~ cutoff, info=true) }}
  {{ return(dates) }}
{% endmacro %}


{% macro date_in_list(column, dates) %}
  {%- if dates | length == 0 -%}
    false
  {%- else -%}
    {{ column }} in ({% for d in dates %}date '{{ d }}'{% if not loop.last %}, {% endif %}{% endfor %})
  {%- endif -%}
{% endmacro %}
