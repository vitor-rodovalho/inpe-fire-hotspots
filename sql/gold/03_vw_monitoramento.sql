-- =============================================================================
-- Monitoramento do modelo em produção: por hora de ingestão, só nos focos de
-- streaming com FRP (uso = 'avaliacao' da vw_previsoes), quantos focos
-- chegaram, quantos eram intensos, quantos o modelo previu como intensos e a
-- acurácia, a precisão e o recall da previsão.
--
-- É o que mostra se o modelo se mantém fora do período de treino. A
-- comparação natural é com o mês de teste (set/2026, docs/model_metrics.md),
-- com o mesmo limiar de decisão de 0,5: acurácia 0,650, precisão 0,183 e
-- recall 0,649. Como a probabilidade não é calibrada, a acurácia fica abaixo
-- dos ~89% de quem sempre responde "não intenso".
--
-- A hora é a da gravação na Silver (ingerido_em), e não a da detecção: com o
-- replay acelerado, a cada hora de ingestão chegam focos de vários dias.
-- Precisão fica nula numa hora em que o modelo não previu nenhum intenso, e
-- recall numa hora sem nenhum intenso real.
--
-- Executar: bash sql/run_sql.sh sql/gold/03_vw_monitoramento.sql
-- =============================================================================

CREATE OR REPLACE VIEW `{{DATASET}}.vw_monitoramento`
OPTIONS (description = 'Acertos do modelo por hora de ingestão, só nos focos de streaming com FRP')
AS
SELECT
  TIMESTAMP_TRUNC(ingerido_em, HOUR) AS hora_ingestao,
  COUNT(*) AS qtd_focos,
  COUNTIF(real_intenso) AS qtd_intensos,
  COUNTIF(previsto_intenso) AS qtd_previstos_intensos,
  COUNTIF(previsto_intenso = real_intenso) / COUNT(*) AS acuracia,
  SAFE_DIVIDE(COUNTIF(previsto_intenso AND real_intenso), COUNTIF(previsto_intenso)) AS precisao,
  SAFE_DIVIDE(COUNTIF(previsto_intenso AND real_intenso), COUNTIF(real_intenso)) AS recall
FROM `{{DATASET}}.vw_previsoes`
WHERE uso = 'avaliacao'
GROUP BY hora_ingestao;
