-- Evidência: valores ausentes depois da limpeza do streaming.
-- Na limpeza, vazio e -999 viram nulo em todas as colunas numéricas
-- (para_float em pipeline/focos_stream/cleaning.py). Uma linha por satélite e,
-- na primeira linha, o total de todos ('TODOS').
-- Executar: bash sql/run_sql.sh sql/evidence/02_missing_values.sql

SELECT
  IF(GROUPING(satelite) = 1, 'TODOS', IFNULL(satelite, '(vazio)')) AS nome_satelite,
  COUNT(*) AS focos,
  COUNTIF(frp IS NULL) AS sem_frp,
  ROUND(100 * COUNTIF(frp IS NULL) / COUNT(*), 1) AS pct_sem_frp,
  COUNTIF(risco_fogo IS NULL) AS sem_risco_fogo,
  COUNTIF(numero_dias_sem_chuva IS NULL) AS sem_dias_sem_chuva,
  COUNTIF(precipitacao IS NULL) AS sem_precipitacao
FROM `{{DATASET}}.silver_focos_streaming`
WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
GROUP BY ROLLUP (satelite)
ORDER BY focos DESC;
