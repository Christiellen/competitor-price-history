{# Faixas de antecedência usadas no painel. A ordem permite classificar a
   faixa no eixo do gráfico. #}

{% macro antecedence_band(days) %}
    case
        when {{ days }} = 0 then 'D0'
        when {{ days }} <= 2 then 'D1-2'
        when {{ days }} <= 6 then 'D3-6'
        when {{ days }} <= 13 then 'D7-13'
        when {{ days }} <= 29 then 'D14-29'
        else 'D30+'
    end
{% endmacro %}

{% macro antecedence_band_order(days) %}
    case
        when {{ days }} = 0 then 1
        when {{ days }} <= 2 then 2
        when {{ days }} <= 6 then 3
        when {{ days }} <= 13 then 4
        when {{ days }} <= 29 then 5
        else 6
    end
{% endmacro %}
