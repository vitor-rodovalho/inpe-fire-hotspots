-- Evidência: latência entre a publicação no Pub/Sub (publicado_em) e a gravação
-- na Silver pelo Dataflow (ingerido_em), em segundos, por minuto de publicação
-- (UTC, 3 horas à frente de Brasília). A primeira linha, com o minuto vazio, é
-- o total do período. Se o replay publicar mais rápido do que o job processa,
-- os focos esperam na fila do Pub/Sub e a latência cresce ao longo do replay;
-- nesse caso, ela mede a fila, e não o pipeline.
-- Para a latência só dos últimos 60 minutos, use sql/demo/02_streaming_latency.sql.
-- Executar: bash sql/run_sql.sh sql/evidence/05_latency_by_minute.sql

WITH latencias AS (
  SELECT
    TIMESTAMP_TRUNC(publicado_em, MINUTE) AS minuto_publicacao_utc,
    TIMESTAMP_DIFF(ingerido_em, publicado_em, MILLISECOND) AS latencia_ms
  FROM `{{DATASET}}.silver_focos_streaming`
  WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
    AND publicado_em IS NOT NULL
)
SELECT
  minuto_publicacao_utc,
  COUNT(*) AS focos,
  ROUND(APPROX_QUANTILES(latencia_ms, 100)[OFFSET(50)] / 1000, 2) AS p50_s,
  ROUND(APPROX_QUANTILES(latencia_ms, 100)[OFFSET(95)] / 1000, 2) AS p95_s,
  ROUND(MAX(latencia_ms) / 1000, 2) AS max_s
FROM latencias
GROUP BY ROLLUP (minuto_publicacao_utc)
ORDER BY minuto_publicacao_utc NULLS FIRST;
