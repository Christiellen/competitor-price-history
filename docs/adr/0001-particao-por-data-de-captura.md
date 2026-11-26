# ADR 0001 - Partição da fato de capturas por data de captura

- **Status:** aceita
- **Data:** 2026-11

## Contexto

As capturas têm duas datas: a da captura e a da saída. O scraper consulta saídas
de até 60 dias à frente, e capturas chegam atrasadas ou são reenviadas com até
alguns dias de atraso. A carga é diária e o volume real é de centenas de milhões
de linhas.

## Opções

1. **Partição por data da saída.** Combina com o filtro do painel, mas cada carga
   diária reescreveria cerca de 60 partições.
2. **Partição por data de ingestão.** Carga trivial, mas nenhuma consulta de
   negócio filtra por ela, então todas leriam a tabela inteira.
3. **Partição por data de captura, cluster por rota, data da saída e concorrente.**

## Decisão

Opção 3, com `insert_overwrite` sobre as datas de captura afetadas (maior data de
ingestão processada menos `lookback_days`). O mart `agg_fare_curve`, reconstruído
por inteiro, é particionado por data da saída, que é como o painel filtra.

## Consequências

- A carga diária reescreve poucas partições, e reenvios atrasados entram sem
  duplicar.
- Consultas por saída na fato dependem do cluster; `analyses/custo_particao_cluster.sql`
  mede essa diferença.
- `insert_overwrite` em vez de `merge`: substituir a partição inteira é
  idempotente e mais barato que comparar chave a chave.
