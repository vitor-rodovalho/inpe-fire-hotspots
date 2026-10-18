-- =============================================================================
-- Bronze, passo 3: confere a carga contra o manifesto do crawler.
--
-- Uma linha por arquivo mensal. A carga está correta quando a coluna
-- "situacao" é 'ok' em todas as linhas.
--
-- Executar: bash sql/run_sql.sh sql/bronze/03_check_bronze.sql
-- =============================================================================

WITH carregado AS (
  SELECT nome_arquivo, COUNT(*) AS linhas_bronze
  FROM `{{DATASET}}.bronze_focos_mensal`
  GROUP BY nome_arquivo
),
esperado AS (
  SELECT uri AS nome_arquivo, linhas AS linhas_manifesto
  FROM `{{DATASET}}.ext_manifesto`
  WHERE tipo = 'mensal'
)
SELECT
  nome_arquivo,
  e.linhas_manifesto,
  c.linhas_bronze,
  CASE
    WHEN c.linhas_bronze IS NULL THEN 'faltou carregar'
    WHEN e.linhas_manifesto IS NULL THEN 'fora do manifesto'
    WHEN c.linhas_bronze = e.linhas_manifesto THEN 'ok'
    ELSE 'contagem diferente'
  END AS situacao
FROM esperado AS e
FULL OUTER JOIN carregado AS c USING (nome_arquivo)
ORDER BY nome_arquivo;
