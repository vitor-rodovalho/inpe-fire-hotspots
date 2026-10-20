-- Evidência do particionamento, parte 1 de 2: focos por estado num único dia.
-- Rodar só a estimativa e comparar os bytes com os de 07_bytes_whole_period.sql,
-- que faz a mesma conta sem filtro de data:
--   DRY_RUN=1 bash sql/run_sql.sh sql/evidence/06_bytes_one_day.sql
-- Com o filtro, a view lê só a partição do dia pedido.

SELECT estado, origem, COUNT(*) AS focos
FROM `{{DATASET}}.vw_focos_unificada`
WHERE data_deteccao = DATE '2026-08-15'
GROUP BY estado, origem
ORDER BY focos DESC;
