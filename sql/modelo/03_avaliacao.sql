-- =============================================================================
-- Avaliação no mês de teste (C4): o modelo e os dois baselines, nos mesmos
-- focos de set/2026 da Gold de treino, com as métricas do ML.EVALUATE.
--
--   modelo_foco_intenso   boosted tree do plano (sql/modelo/01)
--   baseline_logistica    regressão logística com tipo_orbita e hora (sql/modelo/02)
--   baseline_majoritaria  sempre a classe majoritária do treino; não tem score,
--                         então o ROC AUC é 0,5 por definição
--
-- As métricas de classe (precisão, recall, acurácia, F1) usam o limiar de 0,5
-- do ML.EVALUATE. O critério do plano é o ROC AUC: pelo menos 0,70 e ganhar
-- claramente da regressão logística.
--
-- roc_auc_exato é calculado aqui a partir do ML.PREDICT (estatística de
-- Mann-Whitney, empates contando meio). O roc_auc do ML.EVALUATE é aproximado e
-- erra quando há muitos empates: a regressão logística só tem 47 probabilidades
-- distintas, e o ML.EVALUATE dá 0,595 onde o valor exato é 0,649 (o mesmo da
-- C2). No boosted tree, com probabilidades contínuas, os dois batem.
--
-- Executar: bash sql/run_sql.sh sql/modelo/03_avaliacao.sql
-- =============================================================================

WITH
previsoes AS (
  SELECT 'modelo_foco_intenso' AS modelo, foco_intenso,
    (SELECT p.prob FROM UNNEST(predicted_foco_intenso_probs) AS p WHERE p.label) AS prob
  FROM ML.PREDICT(MODEL `{{DATASET}}.modelo_foco_intenso`, (
    SELECT * EXCEPT (conjunto) FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
  UNION ALL
  SELECT 'baseline_logistica' AS modelo, foco_intenso,
    (SELECT p.prob FROM UNNEST(predicted_foco_intenso_probs) AS p WHERE p.label) AS prob
  FROM ML.PREDICT(MODEL `{{DATASET}}.baseline_logistica`, (
    SELECT tipo_orbita, CAST(hora AS STRING) AS hora, foco_intenso
    FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
),
-- Para cada probabilidade distinta, quantos intensos e não intensos a receberam
por_probabilidade AS (
  SELECT modelo, prob, COUNTIF(foco_intenso) AS positivos, COUNTIF(NOT foco_intenso) AS negativos
  FROM previsoes
  GROUP BY modelo, prob
),
-- Cada intenso ganha de todo não intenso com probabilidade menor e empata com os de mesma probabilidade
auc_exato AS (
  SELECT modelo, SUM(positivos * (negativos_abaixo + 0.5 * negativos)) / (SUM(positivos) * SUM(negativos)) AS roc_auc_exato
  FROM (
    SELECT modelo, positivos, negativos,
      IFNULL(SUM(negativos) OVER (PARTITION BY modelo ORDER BY prob
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS negativos_abaixo
    FROM por_probabilidade
  )
  GROUP BY modelo
),
modelo AS (
  SELECT 'modelo_foco_intenso' AS modelo, precision, recall, accuracy, f1_score, log_loss, roc_auc
  FROM ML.EVALUATE(MODEL `{{DATASET}}.modelo_foco_intenso`, (
    SELECT * EXCEPT (conjunto) FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
),
logistica AS (
  SELECT 'baseline_logistica' AS modelo, precision, recall, accuracy, f1_score, log_loss, roc_auc
  FROM ML.EVALUATE(MODEL `{{DATASET}}.baseline_logistica`, (
    SELECT tipo_orbita, CAST(hora AS STRING) AS hora, foco_intenso
    FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
),
-- A classe majoritária vem do treino (a de não intenso, com ~90%)
majoritaria AS (
  SELECT COUNTIF(foco_intenso) * 2 > COUNT(*) AS classe
  FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'treino'
),
baseline_a AS (
  SELECT
    'baseline_majoritaria' AS modelo,
    IF(m.classe, COUNTIF(t.foco_intenso) / COUNT(*), NULL) AS precision,
    IF(m.classe, 1.0, 0.0) AS recall,
    COUNTIF(t.foco_intenso = m.classe) / COUNT(*) AS accuracy,
    CAST(NULL AS FLOAT64) AS f1_score,
    CAST(NULL AS FLOAT64) AS log_loss,
    0.5 AS roc_auc,
    0.5 AS roc_auc_exato
  FROM `{{DATASET}}.gold_treino` AS t
  CROSS JOIN majoritaria AS m
  WHERE t.conjunto = 'teste'
  GROUP BY m.classe
)
SELECT m.*, a.roc_auc_exato FROM modelo AS m JOIN auc_exato AS a USING (modelo)
UNION ALL
SELECT l.*, a.roc_auc_exato FROM logistica AS l JOIN auc_exato AS a USING (modelo)
UNION ALL
SELECT * FROM baseline_a
ORDER BY roc_auc_exato DESC;
