-- =============================================================================
-- Perfil dos dados: responde, sobre a Bronze,
--   1. Quais satélites aparecem e quanto de cada um chega sem FRP;
--   2. A parcela sem FRP por mês;
--   3. Quantos valores vazios e -999 há em cada coluna numérica;
--   4. Se o id é único.
--
-- Os resultados ajudam a conferir a tabela de órbitas, que é gerada da Bronze
-- por sql/reference/01_satelites.sql.
-- Salvar a saída em docs/data_profile.md.
--
-- Executar: bash sql/run_sql.sh sql/bronze/04_data_profile.sql
-- =============================================================================

-- Regra de ausência usada em todo o projeto: vazio ou -999 (depois de aparar)
CREATE TEMP FUNCTION ausente(valor STRING) AS (
  TRIM(IFNULL(valor, '')) = '' OR SAFE_CAST(TRIM(valor) AS FLOAT64) = -999
);

-- 1. Satélites e parcela sem FRP
SELECT
  TRIM(satelite) AS satelite,
  COUNT(*) AS focos,
  COUNTIF(ausente(frp)) AS sem_frp,
  ROUND(100 * COUNTIF(ausente(frp)) / COUNT(*), 1) AS pct_sem_frp
FROM `{{DATASET}}.bronze_focos_mensal`
GROUP BY satelite
ORDER BY focos DESC;

-- 2. Parcela sem FRP por mês
SELECT
  mes_referencia,
  COUNT(*) AS focos,
  COUNTIF(ausente(frp)) AS sem_frp,
  ROUND(100 * COUNTIF(ausente(frp)) / COUNT(*), 1) AS pct_sem_frp
FROM `{{DATASET}}.bronze_focos_mensal`
GROUP BY mes_referencia
ORDER BY mes_referencia;

-- 3. Vazios e -999 por coluna numérica
SELECT
  COUNT(*) AS total,
  COUNTIF(TRIM(IFNULL(frp, '')) = '') AS frp_vazio,
  COUNTIF(SAFE_CAST(TRIM(frp) AS FLOAT64) = -999) AS frp_999,
  COUNTIF(TRIM(IFNULL(risco_fogo, '')) = '') AS risco_fogo_vazio,
  COUNTIF(SAFE_CAST(TRIM(risco_fogo) AS FLOAT64) = -999) AS risco_fogo_999,
  COUNTIF(TRIM(IFNULL(precipitacao, '')) = '') AS precipitacao_vazio,
  COUNTIF(SAFE_CAST(TRIM(precipitacao) AS FLOAT64) = -999) AS precipitacao_999,
  COUNTIF(TRIM(IFNULL(numero_dias_sem_chuva, '')) = '') AS dias_sem_chuva_vazio,
  COUNTIF(SAFE_CAST(TRIM(numero_dias_sem_chuva) AS FLOAT64) = -999) AS dias_sem_chuva_999,
  COUNTIF(SAFE_CAST(TRIM(lat) AS FLOAT64) IS NULL OR SAFE_CAST(TRIM(lon) AS FLOAT64) IS NULL) AS coordenada_invalida,
  COUNTIF(SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', TRIM(data_hora_gmt)) IS NULL) AS data_invalida
FROM `{{DATASET}}.bronze_focos_mensal`;

-- 4. Unicidade do id
SELECT
  COUNT(*) AS linhas,
  COUNT(DISTINCT id) AS ids_distintos,
  COUNT(*) - COUNT(DISTINCT id) AS ids_repetidos
FROM `{{DATASET}}.bronze_focos_mensal`;
