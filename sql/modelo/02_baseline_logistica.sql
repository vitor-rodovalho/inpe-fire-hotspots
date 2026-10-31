-- =============================================================================
-- Baseline B (C4): regressão logística só com tipo_orbita e hora, as duas como
-- categoria, treinada nos mesmos focos de treino do modelo. O plano pede que o
-- modelo ganhe claramente dela no mês de teste. Não é modelo de produto: não é
-- registrado no Vertex AI nem servido pela API.
--
-- É o mesmo baseline da C2 (model/sinal_modelo.py), lá com o scikit-learn:
-- classes equilibradas e hora em one-hot (por isso o CAST para STRING).
--
-- Sem early_stop = FALSE, o BigQuery ML para quando a perda melhora menos de 1%
-- por iteração: na primeira rodada (31/10), parou na 2ª iteração, com a perda
-- quase no valor inicial, e o ROC AUC ficou em 0,581, contra 0,649 na C2. Com
-- as 50 iterações (o máximo do BigQuery ML), o baseline converge como lá.
--
-- Custo: a regressão logística é um modelo interno do BigQuery ML, cobrado a
-- US$ 312,50 por TiB processado. Confira o dry run antes de rodar.
--
-- Executar: DRY_RUN=1 bash sql/run_sql.sh sql/modelo/02_baseline_logistica.sql
--           bash sql/run_sql.sh sql/modelo/02_baseline_logistica.sql
-- =============================================================================

CREATE OR REPLACE MODEL `{{DATASET}}.baseline_logistica`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['foco_intenso'],
  auto_class_weights = TRUE,
  data_split_method = 'NO_SPLIT',
  early_stop = FALSE,
  max_iterations = 50
) AS
SELECT tipo_orbita, CAST(hora AS STRING) AS hora, foco_intenso
FROM `{{DATASET}}.gold_treino`
WHERE conjunto = 'treino';
