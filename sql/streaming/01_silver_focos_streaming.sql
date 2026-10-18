-- =============================================================================
-- Silver de streaming: focos limpos que o Dataflow grava continuamente
-- (de DATA_CORTE em diante, origem = 'streaming').
--
-- Mesmo esquema da silver_focos_historico, para que as duas se unam na view
-- vw_focos_unificada. CREATE TABLE IF NOT EXISTS: rodar de novo nunca apaga
-- o que o streaming já gravou.
--
-- Particionada por dia da detecção com filtro obrigatório: toda consulta
-- precisa dizer quais dias quer ler.
--
-- Executar: bash sql/run_sql.sh sql/streaming/01_silver_focos_streaming.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{{DATASET}}.silver_focos_streaming` (
  id STRING,
  lat FLOAT64,
  lon FLOAT64,
  data_hora_gmt TIMESTAMP,
  satelite STRING,
  municipio STRING,
  estado STRING,
  pais STRING,
  municipio_id INT64,
  estado_id INT64,
  pais_id INT64,
  numero_dias_sem_chuva FLOAT64,
  precipitacao FLOAT64,
  risco_fogo FLOAT64,
  bioma STRING,
  frp FLOAT64 OPTIONS (description = 'Vazio e -999 viram NULL'),
  data_deteccao DATE OPTIONS (description = 'DATE(data_hora_gmt), coluna de partição'),
  origem STRING OPTIONS (description = 'batch ou streaming'),
  publicado_em TIMESTAMP OPTIONS (description = 'Instante em que o replay publicou no Pub/Sub'),
  ingerido_em TIMESTAMP OPTIONS (description = 'Instante em que o Dataflow processou o foco')
)
PARTITION BY data_deteccao
CLUSTER BY estado, satelite
OPTIONS (
  require_partition_filter = TRUE,
  description = 'Focos limpos vindos do streaming (Pub/Sub -> Dataflow)'
);
