-- =============================================================================
-- Agregados calculados pelo Dataflow enquanto os focos chegam: uma linha por
-- janela de 1 hora (pelo horário da DETECÇÃO, não da chegada) e por estado.
--
-- Executar: bash sql/run_sql.sh sql/streaming/03_gold_agregados_janela.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{{DATASET}}.gold_agregados_janela` (
  inicio_janela TIMESTAMP,
  fim_janela TIMESTAMP,
  estado STRING,
  qtd_focos INT64,
  qtd_sem_frp INT64 OPTIONS (description = 'Focos que chegaram sem FRP'),
  frp_medio FLOAT64 OPTIONS (description = 'Média do FRP dos focos que têm FRP'),
  qtd_intensos INT64 OPTIONS (description = 'Focos com FRP acima do limiar da órbita; nulo se limiar_frp estava vazia'),
  calculado_em TIMESTAMP
)
PARTITION BY DATE(inicio_janela)
CLUSTER BY estado
OPTIONS (
  require_partition_filter = TRUE,
  description = 'Agregados por janela de 1 hora e estado, gravados pelo Dataflow'
);
