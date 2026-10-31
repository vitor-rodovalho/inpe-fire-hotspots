-- =============================================================================
-- Modelo do projeto (C4): boosted tree do BigQuery ML que estima a
-- probabilidade de um foco ser intenso, treinado na Gold de treino e
-- registrado no Vertex AI Model Registry com o mesmo nome.
--
-- É o CREATE MODEL do plano ("O modelo"): as variáveis são as colunas da Gold
-- (lat, lon, hora, mes, tipo_orbita, bioma, numero_dias_sem_chuva,
-- precipitacao, risco_fogo), o rótulo é foco_intenso e só entram os focos do
-- conjunto de treino (out/2025 a ago/2026). O teste (set/2026) fica para
-- sql/modelo/03_avaliacao.sql.
--
-- O plano não fixa hiperparâmetros. Os daqui são os da C2
-- (model/sinal_modelo.py, PARAMETROS_XGB), validados nesta mesma divisão por
-- tempo (ROC AUC 0,725 em set/2026), e os mesmos da exportação de brinquedo
-- (C3). O treino usa todos os meses, sem separação automática (NO_SPLIT) e com
-- 300 iterações fixas: o padrão do BigQuery ML sortearia focos do treino para a
-- parada antecipada, e focos vizinhos no tempo e no espaço são quase cópias,
-- então esse sorteio mediria mal e ainda tiraria dados do treino.
--
-- auto_class_weights equilibra as classes (10% de intensos). Por isso a
-- probabilidade não é calibrada: com o limiar de 0,5, o modelo marca mais
-- intensos do que existem.
--
-- Custo: o boosted tree é um modelo externo do BigQuery ML. O treino roda no
-- Vertex AI e é cobrado a US$ 6,25 por TiB, somando o pré-processamento (o
-- dry run) e o tempo de máquina convertido em bytes; nos testes de 20 a 31/10,
-- cada treino levou de 9 a 21 minutos e custou de US$ 0,15 a 0,33.
--
-- Rodar depois da Gold de treino (sql/gold/01_gold_treino.sql). Rodar de novo
-- substitui o modelo e cria uma nova versão no Vertex AI.
--
-- Executar: DRY_RUN=1 bash sql/run_sql.sh sql/modelo/01_modelo_foco_intenso.sql
--           bash sql/run_sql.sh sql/modelo/01_modelo_foco_intenso.sql
-- =============================================================================

CREATE OR REPLACE MODEL `{{DATASET}}.modelo_foco_intenso`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['foco_intenso'],
  auto_class_weights = TRUE,
  data_split_method = 'NO_SPLIT',
  early_stop = FALSE,
  max_iterations = 300,
  max_tree_depth = 6,
  learn_rate = 0.1,
  subsample = 0.8,
  colsample_bytree = 0.8,
  tree_method = 'HIST',
  model_registry = 'VERTEX_AI',
  vertex_ai_model_id = 'modelo_foco_intenso',
  vertex_ai_model_version_aliases = ['v1']
) AS
SELECT * EXCEPT (conjunto)
FROM `{{DATASET}}.gold_treino`
WHERE conjunto = 'treino';
