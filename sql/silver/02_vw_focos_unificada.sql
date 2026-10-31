-- =============================================================================
-- View unificada: histórico e streaming juntos, separados pela data de corte.
--
--   silver_focos_historico  (origem = 'batch')      dias antes de DATA_CORTE
--   silver_focos_streaming  (origem = 'streaming')  dias a partir de DATA_CORTE
--
-- A data de corte garante que nenhum dia venha das duas fontes. O lado do
-- streaming é deduplicado de novo, porque o Pub/Sub entrega cada mensagem
-- pelo menos uma vez e a deduplicação do Beam só cobre 10 minutos. Vale o
-- primeiro foco gravado (menor ingerido_em).
--
-- data_deteccao entra no PARTITION BY da deduplicação (o mesmo id tem sempre
-- o mesmo dia de detecção): assim um filtro de data feito sobre a view chega
-- às partições das duas tabelas, e a consulta lê só os dias que pede.
--
-- As colunas são listadas uma a uma, para que a ordem das duas tabelas nunca
-- desalinhe o UNION ALL.
--
-- Rodar depois da Silver histórica (sql/silver/01) e da Silver de streaming
-- (sql/streaming/01). Rodar de novo só substitui a definição.
--
-- Executar: bash sql/run_sql.sh sql/silver/02_vw_focos_unificada.sql
-- =============================================================================

CREATE OR REPLACE VIEW `{{DATASET}}.vw_focos_unificada`
OPTIONS (description = 'Silver histórica (batch) e de streaming juntas, separadas pela data de corte {{DATA_CORTE}}')
AS
SELECT
  id, lat, lon, data_hora_gmt, satelite, municipio, estado, pais,
  municipio_id, estado_id, pais_id,
  numero_dias_sem_chuva, precipitacao, risco_fogo, bioma, frp,
  data_deteccao, origem, publicado_em, ingerido_em
FROM `{{DATASET}}.silver_focos_historico`
WHERE data_deteccao < DATE '{{DATA_CORTE}}'

UNION ALL

(
  SELECT
    id, lat, lon, data_hora_gmt, satelite, municipio, estado, pais,
    municipio_id, estado_id, pais_id,
    numero_dias_sem_chuva, precipitacao, risco_fogo, bioma, frp,
    data_deteccao, origem, publicado_em, ingerido_em
  FROM `{{DATASET}}.silver_focos_streaming`
  WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY data_deteccao, id ORDER BY ingerido_em) = 1
);
