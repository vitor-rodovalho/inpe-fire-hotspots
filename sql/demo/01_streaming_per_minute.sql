-- Focos de streaming gravados por minuto de ingestão, nos últimos 30 minutos.
-- Na demo, rodar de novo mostra os números crescendo.
-- Executar: bash sql/run_sql.sh sql/demo/01_streaming_per_minute.sql

DECLARE janela_minutos INT64 DEFAULT 30;

SELECT
  TIMESTAMP_TRUNC(ingerido_em, MINUTE) AS minuto_ingestao,
  COUNT(*) AS focos,
  COUNTIF(frp IS NULL) AS sem_frp,
  COUNT(DISTINCT estado) AS estados
FROM `{{DATASET}}.silver_focos_streaming`
WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
  AND ingerido_em >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL janela_minutos MINUTE)
GROUP BY minuto_ingestao
ORDER BY minuto_ingestao DESC;
