-- =============================================================================
-- Previsões do modelo sobre os focos de streaming: cada foco que chega depois
-- da data de corte, com a probabilidade de ser intenso, a classe prevista e,
-- quando o satélite mediu o FRP, o rótulo real.
--
--   uso = 'avaliacao'   foco com FRP: a previsão é comparada com o real
--                       (é o que a vw_monitoramento mede)
--   uso = 'estimativa'  foco sem FRP (METOP-B, METOP-C, MSG-03): a previsão é a
--                       única informação de intensidade, e real_intenso é nulo
--
-- A coluna uso mantém a estimativa sempre separada do que foi medido: nenhuma
-- consulta deve somar as duas.
--
-- As variáveis são preparadas como na Gold de treino (sql/gold/01): hora e mês
-- de data_hora_gmt em GMT e tipo_orbita de satelites. O rótulo real usa o mesmo
-- limiar do treino (frp > limiar da órbita). A classe prevista é a do
-- ML.PREDICT, com o limiar de decisão de 0,5, o mesmo da API.
--
-- A view roda o ML.PREDICT a cada consulta, só nos dias a partir da data de
-- corte, então os números acompanham os focos que o Dataflow grava. Cada
-- consulta lê a Silver de streaming inteira (dezenas de MB) e é cobrada na
-- tarifa de consulta.
--
-- Rodar depois do modelo (sql/modelo/01) e da view unificada (sql/silver/02).
-- Rodar de novo só substitui a definição.
--
-- Executar: bash sql/run_sql.sh sql/gold/02_vw_previsoes.sql
-- =============================================================================

CREATE OR REPLACE VIEW `{{DATASET}}.vw_previsoes`
OPTIONS (description = 'Focos de streaming pontuados pelo modelo_foco_intenso; uso separa avaliação (com FRP) de estimativa (sem FRP)')
AS
WITH novos AS (
  SELECT
    f.id, f.estado, f.municipio, f.satelite, f.data_hora_gmt, f.data_deteccao,
    f.publicado_em, f.ingerido_em, f.frp,
    -- As variáveis do modelo, com os nomes e o cálculo da Gold de treino
    f.lat, f.lon,
    EXTRACT(HOUR FROM f.data_hora_gmt) AS hora,
    EXTRACT(MONTH FROM f.data_hora_gmt) AS mes,
    s.tipo_orbita,
    f.bioma, f.numero_dias_sem_chuva, f.precipitacao, f.risco_fogo
  FROM `{{DATASET}}.vw_focos_unificada` AS f
  JOIN `{{DATASET}}.satelites` AS s USING (satelite)
  WHERE f.data_deteccao >= DATE '{{DATA_CORTE}}'
    AND f.origem = 'streaming'
)
SELECT
  p.id, p.estado, p.municipio, p.satelite, p.tipo_orbita, p.bioma,
  p.lat, p.lon, p.data_hora_gmt, p.data_deteccao, p.publicado_em, p.ingerido_em,
  p.frp,
  (SELECT x.prob FROM UNNEST(p.predicted_foco_intenso_probs) AS x WHERE x.label) AS probabilidade_intenso,
  p.predicted_foco_intenso AS previsto_intenso,
  IF(p.frp IS NULL, NULL, p.frp > l.limiar) AS real_intenso,   -- Nulo: não há o que comparar
  IF(p.frp IS NULL, 'estimativa', 'avaliacao') AS uso
FROM ML.PREDICT(MODEL `{{DATASET}}.modelo_foco_intenso`, (SELECT * FROM novos)) AS p
JOIN `{{DATASET}}.limiar_frp` AS l ON l.tipo_orbita = p.tipo_orbita;
