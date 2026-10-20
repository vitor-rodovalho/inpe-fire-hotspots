-- =============================================================================
-- Referência: calcula e grava o limiar de FRP que define "foco intenso".
--
-- O limiar é o percentil 90 do FRP de cada tipo de órbita, só nos meses de
-- treino (antes de INICIO_TESTE), para que o mês de teste não influencie a
-- regra. É por órbita porque sensores diferentes medem energias diferentes
-- por pixel. O INPE não tem escala oficial de intensidade: o limiar é nosso.
--
-- O notebook 01 chegou a 202,2 MW (geoestacionário) e 28,4 MW (polar) com
-- APPROX_QUANTILES; aqui o cálculo é exato, então o valor pode mudar na
-- casa decimal. A Frente C confere o valor e pode ajustar o percentil.
--
-- Rodar depois da Silver histórica (sql/silver/01) e da tabela vazia
-- (sql/reference/02). A tabela é substituída inteira. Depois:
--   - reinicie o job do Dataflow (drain.sh e deploy.sh), que lê o limiar ao subir;
--   - recrie a Gold de treino (sql/gold/01), que usa o limiar no rótulo.
--
-- Executar: bash sql/run_sql.sh sql/reference/03_calcular_limiar_frp.sql
-- =============================================================================

DECLARE INICIO_TESTE DATE DEFAULT '2026-09-01';  -- O mesmo de sql/gold/01_gold_treino.sql

CREATE TEMP TABLE calculado AS
SELECT DISTINCT
  s.tipo_orbita,
  -- PERCENTILE_CONT só aceita um literal: para mudar o percentil, troque o 0.9
  -- e o 90 gravado abaixo
  PERCENTILE_CONT(f.frp, 0.9) OVER (PARTITION BY s.tipo_orbita) AS limiar,
  COUNT(*) OVER (PARTITION BY s.tipo_orbita) AS focos_com_frp
FROM `{{DATASET}}.silver_focos_historico` AS f
JOIN `{{DATASET}}.satelites` AS s USING (satelite)
WHERE f.data_deteccao < INICIO_TESTE
  AND f.frp IS NOT NULL;

-- Troca numa transação, para quem ler a tabela nunca a encontrar vazia
BEGIN TRANSACTION;
DELETE FROM `{{DATASET}}.limiar_frp` WHERE TRUE;
INSERT INTO `{{DATASET}}.limiar_frp` (tipo_orbita, limiar, percentil, calculado_em)
SELECT tipo_orbita, limiar, 90, CURRENT_TIMESTAMP()
FROM calculado;
COMMIT TRANSACTION;

-- Resultado, para conferir
SELECT l.tipo_orbita, ROUND(l.limiar, 1) AS limiar_mw, l.percentil, c.focos_com_frp, l.calculado_em
FROM `{{DATASET}}.limiar_frp` AS l
JOIN calculado AS c USING (tipo_orbita)
ORDER BY l.tipo_orbita;
