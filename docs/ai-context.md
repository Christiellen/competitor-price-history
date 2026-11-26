# Contexto para agentes de IA

Este arquivo é o contexto que um agente (LLM) recebe antes de consultar os dados
de tarifas. A ideia é tirar do agente as decisões em que a ambiguidade vira
alucinação: qual tabela usar, como agregar e o que um valor nulo significa.

## Regras

1. **Perguntas de preço vão para a camada semântica.** Use as métricas de
   `dbt/models/marts/_semantic.yml` (`our_avg_fare`, `market_avg_fare`,
   `price_index`, `our_sold_out_rate`, `market_sold_out_rate`). Não escreva SQL
   que tira a média de `our_avg_price`, `market_avg_price` ou `price_index`:
   são médias por linha, e a média delas dá número errado.
2. **Compare sempre na mesma antecedência.** Tarifa de hoje para uma saída daqui
   a 30 dias não se compara com tarifa de uma saída de amanhã. Agrupe ou filtre
   por `days_before_departure` ou `antecedence_band`.
3. **Esgotado não é dado faltando.** `price` nulo com `is_sold_out = true` é
   sinal de demanda. Saídas esgotadas entram na taxa de esgotamento e ficam fora
   das médias de tarifa.
4. **Duas datas.** `departure_date` é a data da viagem; `capture_date` é a data
   em que o preço foi visto. "Preço da semana que vem" é filtro em
   `departure_date`. "Como o preço mudou desde segunda" é filtro em
   `capture_date`. Na dúvida, pergunte.
5. **"Nós" é a empresa com `is_own_company = true`** em `dim_competitor`.
6. **Fato de capturas não é para responder preço.** `fct_fare_capture` tem
   várias capturas por saída no mesmo dia; serve para auditoria e qualidade.

## Onde está o significado de cada coisa

| Precisa de | Leia |
|---|---|
| Grão, dono, SLA e uso recomendado de cada tabela | `meta` dos modelos em `dbt/models/marts/_marts.yml` (também no `manifest.json`) |
| Definição de antecedência, índice de preço, posição de preço e esgotamento | `dbt/models/marts/_docs.md` |
| Fórmula de cada métrica | `dbt/models/marts/_semantic.yml` |
| Quem consome cada tabela | `dbt/models/marts/_exposures.yml` |

O `dbt docs generate` publica tudo isso no `target/manifest.json` e no
`catalog.json`, que um agente pode ler como fonte de metadados estruturados.

## Exemplos

| Pergunta | Como responder |
|---|---|
| Estamos mais caros que o mercado em São Paulo - Rio na semana que vem? | `price_index` por `route__route_name`, filtro de `departure_date` na próxima semana. Abaixo de 1 = estamos mais caros. |
| Qual concorrente esgota primeiro no feriado? | `fct_fare_snapshot_daily`, primeira `capture_date` com `is_sold_out` por empresa, nas saídas do feriado. |
| Quantas vezes o concorrente X mudou a tarifa da saída Y? | `fct_fare_interval`: número de períodos da saída. |
