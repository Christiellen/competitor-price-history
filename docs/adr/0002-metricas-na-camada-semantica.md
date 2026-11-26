# ADR 0002 - Métricas de tarifa definidas na camada semântica

- **Status:** aceita
- **Data:** 2026-11

## Contexto

O mart `agg_fare_curve` guarda médias por linha (rota, classe, data da saída e
antecedência). Painel, analistas e agentes de IA agregam essas linhas de jeitos
diferentes. A média de médias e a média do índice de preço por linha dão números
diferentes da média ponderada, e cada consumidor poderia chegar a um resultado
diferente para a mesma pergunta.

## Decisão

- Cada métrica é definida uma vez, no MetricFlow (`models/marts/_semantic.yml`).
- Médias são razões de somas: soma das tarifas dividida pelo número de saídas com
  tarifa.
- `price_index` divide as duas médias ponderadas, calculadas só nas linhas em que
  nós e o mercado temos tarifa, e não tira a média do índice de cada linha.
- O mart continua com as colunas por linha, para o painel detalhado; o contrato
  do mart protege essas colunas.

## Consequências

- Uma definição, vários consumidores: Power BI (medidas DAX equivalentes em
  `powerbi/medidas.dax`), consultas `mf query` e agentes de IA.
- Mudança de regra passa por pull request e pelo CI (`dbt parse` valida o
  manifesto semântico).
- Ainda há duplicação entre DAX e MetricFlow; o próximo passo é o Power BI ler a
  camada semântica diretamente, quando houver integração disponível no ambiente.
