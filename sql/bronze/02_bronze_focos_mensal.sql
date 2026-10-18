-- =============================================================================
-- Bronze, passo 2: carrega os CSVs mensais numa tabela nativa do BigQuery.
--
-- Mantém tudo como texto e acrescenta três colunas de controle:
--   nome_arquivo    : de qual CSV a linha veio (gs://...)
--   mes_referencia  : 1º dia do mês do arquivo, tirado do nome (partição)
--   carregado_em    : instante desta carga
--
-- Particionada por mês do arquivo: recarregar ou consultar um mês só lê aquele
-- mês. A carga recria a tabela inteira, então rodar de novo não duplica nada.
--
-- Executar: bash sql/run_sql.sh sql/bronze/02_bronze_focos_mensal.sql
-- =============================================================================

CREATE OR REPLACE TABLE `{{DATASET}}.bronze_focos_mensal`
PARTITION BY DATE_TRUNC(mes_referencia, MONTH)
CLUSTER BY nome_arquivo
OPTIONS (
  description = 'Focos mensais do INPE como vieram (texto), um registro por linha de CSV'
)
AS
SELECT
  ext.*,
  _FILE_NAME AS nome_arquivo,
  PARSE_DATE('%Y%m%d', CONCAT(REGEXP_EXTRACT(_FILE_NAME, r'focos_mensal_br_(\d{6})'), '01')) AS mes_referencia,
  CURRENT_TIMESTAMP() AS carregado_em
FROM `{{DATASET}}.ext_focos_mensal` AS ext;
