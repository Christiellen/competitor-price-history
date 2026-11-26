-- Rode no console do BigQuery e anote os "bytes processados" de cada consulta
-- (aparece antes de executar). Use os números reais na tabela do README.
-- Troque <projeto> e <dataset> pelos seus.

-- 1) Fato de capturas inteira: lê todas as partições
select avg(price)
from `<projeto>.<dataset>_marts.fct_fare_capture`;

-- 2) Uma semana de captura: partition pruning (lê 7 partições)
select avg(price)
from `<projeto>.<dataset>_marts.fct_fare_capture`
where capture_date between date '2026-11-01' and date '2026-11-07';

-- 3) Uma semana + uma rota e uma data de saída: o cluster reduz os blocos lidos
select avg(price)
from `<projeto>.<dataset>_marts.fct_fare_capture`
where capture_date between date '2026-11-01' and date '2026-11-07'
  and route_id = 1
  and departure_date = date '2026-11-20';

-- 4) Curva de uma saída sem filtrar a data da captura: lê todas as partições,
--    mesmo com o cluster. É o custo da escolha "partição por data de captura".
select days_before_departure, avg(price)
from `<projeto>.<dataset>_marts.fct_fare_capture`
where route_id = 1 and departure_date = date '2026-11-20'
group by 1;

-- 5) A mesma curva no mart particionado por data da SAÍDA: lê uma partição
select days_before_departure, our_avg_price, market_avg_price
from `<projeto>.<dataset>_marts.agg_fare_curve`
where route_id = 1 and departure_date = date '2026-11-20';
