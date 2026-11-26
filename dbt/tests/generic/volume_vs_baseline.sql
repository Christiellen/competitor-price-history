{#
    Volume: compara a quantidade de linhas do dia mais recente com a média dos
    dias anteriores. Falha quando a razão sai da faixa [min_ratio, max_ratio].

    Pega o que contract e testes de grão não pegam: o scraper de um concorrente
    que parou (volume cai) ou um reenvio em massa (volume dobra).

    O dia de referência é o maior valor de date_column na própria tabela, e não
    current_date(), para o teste funcionar igual em dados históricos e no CI.
    ignore_latest_day: use quando o último dia ainda está em carga (parcial).
#}
{% test volume_vs_baseline(model, date_column, lookback_days=7, min_ratio=0.5, max_ratio=2.0, ignore_latest_day=false) %}

with bounds as (

    select
        {% if ignore_latest_day %}
        date_sub(max({{ date_column }}), interval 1 day)
        {% else %}
        max({{ date_column }})
        {% endif %}                                                   as reference_day
    from {{ model }}

),

daily as (

    select
        m.{{ date_column }}                                           as day,
        count(*)                                                      as row_count
    from {{ model }} as m
    cross join bounds as b
    where m.{{ date_column }} between date_sub(b.reference_day, interval {{ lookback_days }} day)
                                  and b.reference_day
    group by 1

),

comparison as (

    select
        d.day                                                         as reference_day,
        d.row_count,
        (select avg(row_count) from daily where day < d.day)          as baseline_avg,
        (select count(*) from daily where day < d.day)                as baseline_days
    from daily as d
    join bounds as b on d.day = b.reference_day

)

select
    reference_day,
    row_count,
    round(baseline_avg, 1)                                            as baseline_avg,
    round(safe_divide(row_count, baseline_avg), 3)                    as ratio
from comparison
-- sem histórico suficiente não há o que comparar
where baseline_days >= 3
  and (
      safe_divide(row_count, baseline_avg) < {{ min_ratio }}
      or safe_divide(row_count, baseline_avg) > {{ max_ratio }}
  )

{% endtest %}
