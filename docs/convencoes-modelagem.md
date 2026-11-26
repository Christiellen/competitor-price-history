# Convenções de modelagem

## Camadas e nomes

| Camada | Prefixo | Materialização | Regra |
|---|---|---|---|
| staging | `stg_<fonte>__<tabela>` | view | um para um com a fonte: tipos, nomes e textos padronizados. Sem join. |
| intermediate | `int_<o que faz>` | view | passos de lógica reutilizados por mais de um mart. Não é consumido fora do dbt. |
| marts | `fct_`, `dim_`, `agg_` | table ou incremental | o que painéis, analistas e agentes consomem. |
| snapshots | `snap_<tabela>` | snapshot | histórico SCD 2 de cadastros da raw. |

## Toda fato e todo agregado declaram

- **grão** em `meta.grain` e um teste `unique_combination_of_columns` nesse grão;
- **dono** em `meta.owner` e **SLA** em `meta.freshness_sla`;
- **`meta.ai_context`**: quando usar a tabela e o erro mais provável de quem a consulta;
- **contract** quando o modelo tem consumidor fora do dbt (painel, outro time).

## Incremental

- Incremental só quando a carga completa deixa de caber no SLA ou no custo.
- `insert_overwrite` por partição; janela de reprocessamento em `lookback_days`.
- O CI roda o build duas vezes, para testar o caminho `is_incremental()`.

## Testes

| Tipo | Severidade padrão |
|---|---|
| Grão, chaves, integridade com dimensões, contract | erro |
| Schema da fonte (`has_expected_columns`) | erro |
| Volume (`volume_vs_baseline`), de-para faltando, variação de preço | alerta |
| Lógica com casos de borda (ex.: gaps and islands) | teste unitário |

Alerta é para o que pode ser legítimo (feriado, rota nova) e precisa de alguém
olhando antes de parar a carga.

## Decisões de arquitetura

Decisões que mudam grão, partição, materialização ou definição de métrica viram
ADR em `docs/adr/`, numerado, com contexto, opções, decisão e consequências.
