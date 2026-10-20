-- =============================================================================
-- Silver, conferência: três checagens, cada uma com a coluna "situacao".
-- A carga está correta quando "situacao" é 'ok' em todas as linhas.
--
--   1. Contagem por mês: Bronze contra Silver histórica. A diferença é o que
--      01_silver_focos_historico.sql descartou (esperado: zero ou quase).
--   2. Ids repetidos na Silver histórica (esperado: nenhum).
--   3. Esquema: as duas Silvers com as mesmas colunas, tipos e ordem, que é o
--      que a vw_focos_unificada pressupõe.
--
-- Executar: bash sql/run_sql.sh sql/silver/03_check_silver.sql
-- =============================================================================

-- 1. Contagem por mês
WITH bronze AS (
  SELECT mes_referencia AS mes, COUNT(*) AS focos_bronze
  FROM `{{DATASET}}.bronze_focos_mensal`
  GROUP BY mes
),
silver AS (
  SELECT DATE_TRUNC(data_deteccao, MONTH) AS mes, COUNT(*) AS focos_silver
  FROM `{{DATASET}}.silver_focos_historico`
  WHERE data_deteccao < DATE '{{DATA_CORTE}}'
  GROUP BY mes
)
SELECT
  mes,
  b.focos_bronze,
  s.focos_silver,
  b.focos_bronze - s.focos_silver AS descartados,
  CASE
    WHEN s.focos_silver IS NULL THEN 'mês sem focos na Silver'
    WHEN b.focos_bronze IS NULL THEN 'mês fora da Bronze'
    WHEN s.focos_silver = b.focos_bronze THEN 'ok'
    ELSE 'com descartes: ver o resumo de 01_silver_focos_historico.sql'
  END AS situacao
FROM bronze AS b
FULL OUTER JOIN silver AS s USING (mes)
ORDER BY mes;

-- 2. Ids repetidos
SELECT
  COUNT(*) AS focos,
  COUNT(DISTINCT id) AS ids_distintos,
  IF(COUNT(*) = COUNT(DISTINCT id), 'ok', 'ids repetidos') AS situacao
FROM `{{DATASET}}.silver_focos_historico`
WHERE data_deteccao < DATE '{{DATA_CORTE}}';

-- 3. Esquema das duas Silvers
WITH colunas AS (
  SELECT table_name, ordinal_position, column_name, data_type
  FROM `{{DATASET}}.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name IN ('silver_focos_historico', 'silver_focos_streaming')
),
historico AS (SELECT * FROM colunas WHERE table_name = 'silver_focos_historico'),
streaming AS (SELECT * FROM colunas WHERE table_name = 'silver_focos_streaming')
SELECT
  ordinal_position,
  h.column_name AS coluna_historico,
  h.data_type AS tipo_historico,
  s.column_name AS coluna_streaming,
  s.data_type AS tipo_streaming,
  IF(h.column_name = s.column_name AND h.data_type = s.data_type, 'ok', 'diferente') AS situacao
FROM historico AS h
FULL OUTER JOIN streaming AS s USING (ordinal_position)
ORDER BY ordinal_position;
