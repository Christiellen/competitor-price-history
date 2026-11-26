{% docs antecedence %}
**Antecedência**: dias entre a data da captura (local, America/Sao_Paulo) e a
data da saída. Zero é o próprio dia da viagem. É o eixo da precificação no
rodoviário: a tarifa tende a subir conforme a saída se aproxima. Duas tarifas
só são comparáveis na mesma antecedência.
{% enddocs %}

{% docs price_index %}
**Índice de preço**: tarifa média do mercado dividida pela nossa, na mesma rota,
classe, data da saída e antecedência. Acima de 1, o mercado está mais caro (nós
estamos mais baratos); abaixo de 1, estamos mais caros. Nulo quando um dos dois
lados não tem tarifa (saída esgotada ou sem oferta). Para agregar várias linhas,
use a métrica `price_index` da camada semântica (ou a medida Índice de Tarifa do
Power BI): ela divide as médias ponderadas pelas saídas com tarifa, só nas linhas
em que os dois lados têm tarifa. Não tire a média deste campo.
{% enddocs %}

{% docs price_position %}
**Posição de preço**: onde a nossa tarifa média cai em relação à faixa do
mercado (mínima e máxima dos concorrentes) na mesma antecedência. Valores:
`mais barato que todos`, `dentro da faixa`, `mais caro que todos`,
`sem tarifa nossa`, `sem tarifa do mercado`.
{% enddocs %}

{% docs sold_out %}
**Esgotado**: a saída aparece no site sem assento disponível e, portanto, sem
tarifa. Não é dado faltando: é sinal de demanda. Saídas esgotadas entram na
contagem de saídas e na taxa de esgotamento, mas não nas médias de tarifa.
{% enddocs %}
