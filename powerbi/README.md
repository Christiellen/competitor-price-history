# Painel Power BI - Tarifas da Concorrência no Rodoviário

O painel lê a camada `marts` gerada pelo dbt no BigQuery. Toda a regra de
negócio (deduplicação, de-para de cidades e classes, antecedência, períodos de
tarifa, posição frente ao mercado) fica no dbt: o Power BI só relaciona as
tabelas e calcula as medidas.

| Arquivo | Conteúdo |
|---|---|
| `medidas.dax` | Todas as medidas DAX, comentadas |
| `tema-precos.json` | Tema de cores e fontes (Exibir > Temas > Procurar temas) |

O `.pbix` não está versionado: é binário e contém os dados importados. Depois de
montar o painel, salve os prints em `docs/` e, se quiser versionar o relatório,
salve como **Projeto do Power BI (.pbip)**, que gera arquivos de texto.

## 1. Conectar ao BigQuery

1. Power BI Desktop > **Obter dados** > **Google BigQuery** > entrar com a conta Google.
2. Navegue até `<seu-projeto>` > `<dataset>_marts` (por exemplo `dev_marts`).
3. Selecione as tabelas e clique em **Transformar dados**:

| Tabela no BigQuery | Nome no Power BI | Papel |
|---|---|---|
| `agg_fare_curve` | `Curva` | fato principal: rota x classe x saída x antecedência |
| `fct_fare_snapshot_daily` | `Tarifa` | fato: empresa x saída x classe x dia de captura |
| `fct_fare_interval` | `Periodo` | fato: períodos de mesma tarifa |
| `dim_route` | `Rota` | dimensão |
| `dim_service_class` | `Classe` | dimensão |
| `dim_competitor` | `Empresa` | dimensão (inclui a nossa, `is_own_company`) |
| `dim_date` | `DataSaida` | dimensão de datas, papel "data da saída" |
| `dim_date` (Referência) | `DataCaptura` | dimensão de datas, papel "data da captura" |

Para o segundo papel da data, clique com o botão direito em `DataSaida` no
Power Query > **Referência** e renomeie para `DataCaptura`.

**Import x DirectQuery.** Com o volume padrão (cerca de 500 mil linhas na curva
e 2,2 milhões no snapshot), **Import** é a melhor escolha. Com o volume real,
importe a `Curva` com **atualização incremental** (parâmetros `RangeStart` e
`RangeEnd` filtrando `departure_date`, o que aproveita a partição) e deixe a
`Tarifa` em DirectQuery ou fora do modelo.

## 2. Modelo

Marque `DataSaida` como tabela de datas (coluna `date_day`).

```
DataSaida[date_day]    1 ──* Curva[departure_date]
DataCaptura[date_day]  1 ──* Curva[capture_date]
DataSaida[date_day]    1 ──* Tarifa[departure_date]
DataCaptura[date_day]  1 ──* Tarifa[capture_date]
DataSaida[date_day]    1 ──* Periodo[departure_date]
Rota[route_id]         1 ──* Curva[route_id]        (e Tarifa, Periodo)
Classe[class_code]     1 ──* Curva[class_code]      (e Tarifa, Periodo)
Empresa[competitor_id] 1 ──* Tarifa[competitor_id]  (e Periodo)
Empresa[competitor_id] 1 ┄┄* Curva[cheapest_competitor_id]   (INATIVO)
```

Todos com filtro em direção única, das dimensões para as fatos.

Ajustes de coluna:
- Oculte as chaves (`*_id`, `*_key`) e `ingested_at`.
- `Curva[antecedence_band]`: classificar por `antecedence_band_order`.
- `DataSaida[month_short_pt]`: classificar por `month`; `day_name_pt`: por `day_of_week`.
- Preços em moeda (R$), `price_index` com 3 casas, medidas de % em percentual.

## 3. Medidas

Crie uma tabela vazia `_Medidas` (Inserir dados > OK) e cole as medidas de
`medidas.dax`. As principais:

| Medida | Leitura |
|---|---|
| `Índice de Tarifa` | tarifa média do mercado ÷ a nossa, na mesma antecedência. Acima de 1, estamos mais baratos |
| `% Mais Caros que Todos` | em quanto das combinações comparáveis estamos acima de todos os concorrentes |
| `Distância para o Mais Barato` | quanto estamos acima (ou abaixo) do concorrente mais barato |
| `Taxa de Esgotamento` | sinal de demanda: quem esgota mais e com que antecedência |
| `Mudanças por Saída` | quem pratica precificação dinâmica (perto de zero = tarifa fixa) |
| `Vezes que Foi o Mais Barato` | quem lidera em preço |

## 4. Páginas

**Visão geral**
- Título dinâmico (`Título Índice`) e subtítulo (`Data da Última Captura`).
- Cartões: `Índice de Tarifa`, `Variação do Índice (7 dias)`, `% Mais Caros que Todos`, `Saídas Monitoradas`.
- Linha: `Índice de Tarifa` por `DataSaida[date_day]`, com linha de referência em 1.
- Barras: `% Mais Caros que Todos` por `Rota[city_pair]`.
- Segmentações: classe, rota, período da saída.

**Curva de antecedência**
- Linhas: `Nossa Tarifa Média` e `Tarifa Média do Mercado` por `Curva[days_before_departure]` (eixo invertido: 60 à esquerda, 0 à direita). É o gráfico central do painel.
- Colunas: `Índice de Tarifa` por `antecedence_band`.
- Linhas: `Taxa de Esgotamento - Nossa` e `- Mercado` por `days_before_departure`.
- Matriz: rota x faixa de antecedência com `Distância para o Mais Barato` (formatação condicional).

**Concorrentes**
- Barras: `Mudanças por Saída` por empresa (revela quem tem tarifa fixa).
- Colunas: `Vezes que Foi o Mais Barato` por empresa.
- Dispersão: `Taxa de Esgotamento` (X) x `Tarifa Média` (Y), um ponto por empresa.
- Matriz: empresa x classe com `Tarifa Média` e `Variação Média por Mudança`.

**Saída (detalhe)**
- Segmentações: rota, classe e data da saída (seleção única).
- Linhas em degrau: `Tarifa Média` por `DataCaptura[date_day]`, legenda = empresa.
- Tabela de `Periodo`: empresa, `price`, `is_sold_out`, `valid_from`, `valid_to`, `days_before_departure_start`, `pct_change_from_previous`.

## 5. Atualização

- Power BI Service: publique e configure a credencial do BigQuery no conjunto de
  dados (OAuth da conta Google). O conector do BigQuery não precisa de gateway.
- Agende a atualização para depois do `dbt build` (por exemplo, dbt às 6h e
  Power BI às 7h).
