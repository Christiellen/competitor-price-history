{#
    Schema: confere se a tabela tem as colunas que os modelos esperam.

    O contract protege as tabelas que NÓS publicamos. Este teste protege a
    entrada: se o scraper renomear ou remover uma coluna da raw, o build para
    no teste da fonte, com a lista do que falta, em vez de quebrar no meio do
    staging com um erro de SQL difícil de ler.

    Colunas a mais não falham: a origem pode crescer sem quebrar ninguém.
#}
{% test has_expected_columns(model, column_names) %}

{%- set missing = [] -%}
{%- if execute -%}
    {%- set actual = adapter.get_columns_in_relation(model) | map(attribute='name') | map('lower') | list -%}
    {%- for col in column_names -%}
        {%- if col | lower not in actual -%}
            {%- do missing.append(col) -%}
        {%- endif -%}
    {%- endfor -%}
{%- endif %}

select '{{ missing | join(", ") }}' as missing_columns
from (select 1) as one_row
where {{ 'true' if missing else 'false' }}

{% endtest %}
