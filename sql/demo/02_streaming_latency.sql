-- Latência entre a publicação no Pub/Sub e a gravação pelo Dataflow
-- (publicado_em -> ingerido_em), em segundos.
-- Executar: bash sql/run_sql.sh sql/demo/02_streaming_latency.sql

DECLARE janela_minutos INT64 DEFAULT 60;

SELECT
  COUNT(*) AS focos,
  ROUND(AVG(TIMESTAMP_DIFF(ingerido_em, publicado_em, MILLISECOND)) / 1000, 2) AS media_s,
  ROUND(APPROX_QUANTILES(TIMESTAMP_DIFF(ingerido_em, publicado_em, MILLISECOND), 100)[OFFSET(50)] / 1000, 2) AS p50_s,
  ROUND(APPROX_QUANTILES(TIMESTAMP_DIFF(ingerido_em, publicado_em, MILLISECOND), 100)[OFFSET(95)] / 1000, 2) AS p95_s,
  ROUND(MAX(TIMESTAMP_DIFF(ingerido_em, publicado_em, MILLISECOND)) / 1000, 2) AS max_s
FROM `{{DATASET}}.silver_focos_streaming`
WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
  AND publicado_em IS NOT NULL
  AND ingerido_em >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL janela_minutos MINUTE);
