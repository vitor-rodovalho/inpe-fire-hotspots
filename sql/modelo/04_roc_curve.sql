-- =============================================================================
-- Curva ROC do modelo no mês de teste (C4): para cada limiar de decisão, o
-- recall, a taxa de falsos positivos e a matriz de confusão, com a precisão
-- calculada a partir dela.
--
-- Mostra o que o limiar de 0,5 do ML.EVALUATE esconde: como a probabilidade não
-- é calibrada (auto_class_weights), outro limiar pode equilibrar melhor
-- precisão e recall.
--
-- Executar: bash sql/run_sql.sh sql/modelo/04_roc_curve.sql
-- =============================================================================

SELECT
  threshold AS limiar,
  recall,
  false_positive_rate AS taxa_falsos_positivos,
  SAFE_DIVIDE(true_positives, true_positives + false_positives) AS precisao,
  true_positives, false_positives, true_negatives, false_negatives
FROM ML.ROC_CURVE(MODEL `{{DATASET}}.modelo_foco_intenso`, (
  SELECT * EXCEPT (conjunto) FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
ORDER BY limiar;
