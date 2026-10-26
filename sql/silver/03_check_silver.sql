-- =============================================================================
-- Silver, conferência: uma tabela só, com a coluna "situacao". A carga está
-- correta quando "situacao" é 'ok' em todas as linhas.
--
--   1. Contagem por mês: Bronze contra Silver histórica. A diferença é o que
--      01_silver_focos_historico.sql descartou (esperado: zero ou quase).
--   2. Ids distintos contra o total de focos da Silver histórica.
--   3. Esquema: quantas colunas das duas Silvers coincidem em nome, tipo e
--      posição, que é o que a vw_focos_unificada pressupõe.
--
-- Executar: bash sql/run_sql.sh sql/silver/03_check_silver.sql
-- =============================================================================

WITH bronze AS (
  SELECT mes_referencia AS mes, COUNT(*) AS focos
  FROM `{{DATASET}}.bronze_focos_mensal`
  GROUP BY mes
),
silver AS (
  SELECT DATE_TRUNC(data_deteccao, MONTH) AS mes, COUNT(*) AS focos
  FROM `{{DATASET}}.silver_focos_historico`
  WHERE data_deteccao < DATE '{{DATA_CORTE}}'
  GROUP BY mes
),
ids AS (
  SELECT COUNT(*) AS focos, COUNT(DISTINCT id) AS ids_distintos
  FROM `{{DATASET}}.silver_focos_historico`
  WHERE data_deteccao < DATE '{{DATA_CORTE}}'
),
colunas AS (
  SELECT table_name, ordinal_position, column_name, data_type
  FROM `{{DATASET}}.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name IN ('silver_focos_historico', 'silver_focos_streaming')
),
historico AS (SELECT * FROM colunas WHERE table_name = 'silver_focos_historico'),
streaming AS (SELECT * FROM colunas WHERE table_name = 'silver_focos_streaming')

SELECT
  1 AS ordem,
  CONCAT('contagem ', FORMAT_DATE('%Y-%m', mes)) AS verificacao,
  b.focos AS esperado,
  s.focos AS obtido,
  CASE
    WHEN s.focos IS NULL THEN 'mês sem focos na Silver'
    WHEN b.focos IS NULL THEN 'mês fora da Bronze'
    WHEN s.focos = b.focos THEN 'ok'
    ELSE 'com descartes: ver o resumo de 01_silver_focos_historico.sql'
  END AS situacao
FROM bronze AS b
FULL OUTER JOIN silver AS s USING (mes)

UNION ALL

SELECT 2, 'ids distintos (esperado = total de focos)', focos, ids_distintos,
  IF(focos = ids_distintos, 'ok', 'ids repetidos')
FROM ids

UNION ALL

SELECT
  3,
  'colunas iguais às da silver_focos_streaming',
  (SELECT COUNT(*) FROM streaming),
  COUNT(*),
  IF(COUNT(*) = (SELECT COUNT(*) FROM streaming) AND COUNT(*) = (SELECT COUNT(*) FROM historico),
     'ok', 'diferente')
FROM historico AS h
JOIN streaming AS s USING (ordinal_position)
WHERE h.column_name = s.column_name
  AND h.data_type = s.data_type

ORDER BY ordem, verificacao;
