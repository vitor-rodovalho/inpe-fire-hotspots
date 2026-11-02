-- =============================================================================
-- Importância das variáveis do modelo (C7), pelo ML.FEATURE_IMPORTANCE.
--
--   importance_gain    quanto as divisões que usam a variável melhoram o modelo,
--                      somado nas 300 árvores (a medida principal)
--   importance_weight  quantas vezes a variável é usada numa divisão
--   importance_cover   quantos focos passam pelas divisões que a usam
--
-- pct_ganho é a participação de cada variável no ganho total. Só lê os
-- metadados do modelo: não processa dados nem custa nada.
--
-- Executar: bash sql/run_sql.sh sql/modelo/05_importancia_variaveis.sql
-- =============================================================================

SELECT
  feature AS variavel,
  importance_gain AS ganho,
  ROUND(100 * importance_gain / SUM(importance_gain) OVER (), 1) AS pct_ganho,
  importance_weight AS vezes_usada,
  importance_cover AS cobertura
FROM ML.FEATURE_IMPORTANCE(MODEL `{{DATASET}}.modelo_foco_intenso`)
ORDER BY ganho DESC;
