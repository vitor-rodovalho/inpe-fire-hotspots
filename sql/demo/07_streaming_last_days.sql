-- Focos de streaming por dia de detecção, nos 3 dias mais recentes que têm
-- dados, pela view unificada. É onde o replay está gravando: na demo, rodar de
-- novo mostra a contagem do dia crescendo. Separada da 06 porque o bq mostra só
-- o resultado da última consulta de cada arquivo.
-- Executar: bash sql/run_sql.sh sql/demo/07_streaming_last_days.sql

SELECT
  data_deteccao,
  COUNT(*) AS focos,
  COUNTIF(frp IS NULL) AS sem_frp,
  MAX(ingerido_em) AS ultima_ingestao
FROM `{{DATASET}}.vw_focos_unificada`
WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
  AND origem = 'streaming'
GROUP BY data_deteccao
ORDER BY data_deteccao DESC
LIMIT 3;
