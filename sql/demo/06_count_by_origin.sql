-- Focos por origem na view unificada: o histórico parado e o streaming
-- crescendo. Na demo, rodar de novo enquanto o replay publica mostra os
-- números de 'streaming' subindo e os de 'batch' iguais.
-- Executar: bash sql/run_sql.sh sql/demo/06_count_by_origin.sql

SELECT
  origem,
  COUNT(*) AS focos,
  COUNTIF(frp IS NULL) AS sem_frp,
  MIN(data_deteccao) AS primeiro_dia,
  MAX(data_deteccao) AS ultimo_dia,
  COUNT(DISTINCT data_deteccao) AS dias,
  MAX(ingerido_em) AS ultima_ingestao
FROM `{{DATASET}}.vw_focos_unificada`
GROUP BY origem
ORDER BY primeiro_dia;

-- Streaming nos últimos dias de detecção, que é onde o replay está gravando
SELECT
  data_deteccao,
  COUNT(*) AS focos,
  COUNTIF(frp IS NULL) AS sem_frp,
  MAX(ingerido_em) AS ultima_ingestao
FROM `{{DATASET}}.vw_focos_unificada`
WHERE data_deteccao >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
GROUP BY data_deteccao
ORDER BY data_deteccao DESC;
