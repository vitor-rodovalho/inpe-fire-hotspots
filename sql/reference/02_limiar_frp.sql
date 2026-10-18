-- =============================================================================
-- Referência: limiar de FRP que define "foco intenso", por tipo de órbita.
--
-- Esta etapa só cria a tabela vazia. Enquanto ela estiver azia, o streaming
-- grava qtd_intensos como nulo nos agregados.
--
-- Executar: bash sql/run_sql.sh sql/reference/02_limiar_frp.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{{DATASET}}.limiar_frp` (
  tipo_orbita STRING NOT NULL,
  limiar FLOAT64 NOT NULL OPTIONS (description = 'FRP em MW acima do qual o foco é intenso'),
  percentil INT64 OPTIONS (description = 'Percentil usado no cálculo, por exemplo 90'),
  calculado_em TIMESTAMP
)
OPTIONS (description = 'Limiar de FRP por tipo de órbita (Frente C)');
