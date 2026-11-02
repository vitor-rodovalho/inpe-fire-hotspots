-- O modelo em produção: acurácia, precisão e recall nos focos de streaming com
-- FRP (todas as horas e só a última hora de ingestão), ao lado do mês de teste
-- (set/2026), com o mesmo limiar de decisão de 0,5. Na demo, rodar de novo
-- enquanto o replay publica mostra a última hora mudando. A última linha conta
-- os focos sem FRP, que só recebem a estimativa e ficam fora das métricas.
-- Executar: bash sql/run_sql.sh sql/demo/08_model_monitoring.sql

WITH
teste AS (
  SELECT
    'mês de teste (set/2026)' AS periodo,
    (SELECT COUNT(*) FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste') AS focos,
    accuracy AS acuracia, precision AS precisao, recall
  FROM ML.EVALUATE(MODEL `{{DATASET}}.modelo_foco_intenso`, (
    SELECT * EXCEPT (conjunto) FROM `{{DATASET}}.gold_treino` WHERE conjunto = 'teste'))
),
previsoes AS (
  SELECT * FROM `{{DATASET}}.vw_previsoes`
),
streaming AS (
  SELECT
    'streaming, todas as horas' AS periodo,
    COUNT(*) AS focos,
    COUNTIF(previsto_intenso = real_intenso) / COUNT(*) AS acuracia,
    SAFE_DIVIDE(COUNTIF(previsto_intenso AND real_intenso), COUNTIF(previsto_intenso)) AS precisao,
    SAFE_DIVIDE(COUNTIF(previsto_intenso AND real_intenso), COUNTIF(real_intenso)) AS recall
  FROM previsoes
  WHERE uso = 'avaliacao'
),
ultima_hora AS (
  SELECT
    CONCAT('streaming, última hora (', FORMAT_TIMESTAMP('%d/%m %H:00', hora_ingestao), ' UTC)') AS periodo,
    qtd_focos AS focos, acuracia, precisao, recall
  FROM `{{DATASET}}.vw_monitoramento`
  ORDER BY hora_ingestao DESC
  LIMIT 1
),
estimativas AS (
  SELECT
    'streaming sem FRP (só estimativa)' AS periodo,
    COUNT(*) AS focos,
    CAST(NULL AS FLOAT64) AS acuracia, CAST(NULL AS FLOAT64) AS precisao, CAST(NULL AS FLOAT64) AS recall
  FROM previsoes
  WHERE uso = 'estimativa'
)
SELECT * EXCEPT (ordem)
FROM (
  SELECT 1 AS ordem, * FROM teste
  UNION ALL SELECT 2, * FROM streaming
  UNION ALL SELECT 3, * FROM ultima_hora
  UNION ALL SELECT 4, * FROM estimativas
)
ORDER BY ordem;
