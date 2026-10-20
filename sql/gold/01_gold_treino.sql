-- =============================================================================
-- Gold de treino: as variáveis do modelo, o rótulo e o conjunto de cada foco
-- do histórico.
--
-- Variáveis: só o que se sabe no instante da detecção. Os nomes e o cálculo são
-- os mesmos da API (api/app/features.py), para que o modelo receba lá o mesmo
-- que viu aqui:
--   lat, lon, hora e mes (de data_hora_gmt, em GMT), tipo_orbita (de
--   satelites), bioma, numero_dias_sem_chuva, precipitacao, risco_fogo.
--
-- Rótulo: foco_intenso = frp > limiar da órbita (limiar_frp). O FRP não entra
-- como variável, porque é o que se quer estimar.
--
-- Conjunto: divisão por tempo, não por sorteio (focos vizinhos são quase
-- cópias). Treino de out/2025 a ago/2026, teste em set/2026.
--
-- Ficam de fora:
--   - focos sem FRP, porque não têm rótulo;
--   - focos sem bioma, porque a API recusa bioma nulo e o treino deve ver o
--     mesmo que o serviço.
--
-- O modelo treina com: SELECT * EXCEPT (conjunto) FROM gold_treino WHERE conjunto = 'treino'
--
-- Rodar depois do limiar (sql/reference/03) e da view (sql/silver/02). A
-- tabela é recriada inteira. Ao final, mostra a proporção de positivos, que
-- vai para a Frente C.
--
-- Executar: bash sql/run_sql.sh sql/gold/01_gold_treino.sql
-- =============================================================================

DECLARE INICIO_TESTE DATE DEFAULT '2026-09-01';  -- O mesmo de sql/reference/03_calcular_limiar_frp.sql

ASSERT (SELECT COUNT(DISTINCT tipo_orbita) FROM `{{DATASET}}.limiar_frp`)
     = (SELECT COUNT(DISTINCT tipo_orbita) FROM `{{DATASET}}.satelites`)
AS 'limiar_frp sem todas as órbitas: rode sql/reference/03_calcular_limiar_frp.sql antes';

CREATE OR REPLACE TABLE `{{DATASET}}.gold_treino`
CLUSTER BY conjunto
OPTIONS (description = 'Variáveis do modelo foco intenso, rótulo e conjunto (treino ou teste), do histórico')
AS
SELECT
  f.lat,
  f.lon,
  EXTRACT(HOUR FROM f.data_hora_gmt) AS hora,
  EXTRACT(MONTH FROM f.data_hora_gmt) AS mes,
  s.tipo_orbita,
  f.bioma,
  f.numero_dias_sem_chuva,
  f.precipitacao,
  f.risco_fogo,
  f.frp > l.limiar AS foco_intenso,
  IF(f.data_deteccao >= INICIO_TESTE, 'teste', 'treino') AS conjunto
FROM `{{DATASET}}.vw_focos_unificada` AS f
JOIN `{{DATASET}}.satelites` AS s USING (satelite)
JOIN `{{DATASET}}.limiar_frp` AS l USING (tipo_orbita)
WHERE f.data_deteccao < DATE '{{DATA_CORTE}}'
  AND f.origem = 'batch'
  AND f.frp IS NOT NULL
  AND f.bioma IS NOT NULL;

-- Resultado, para conferir. No treino, os positivos devem ficar perto de 10%
-- em cada órbita, porque o limiar é o percentil 90 desses mesmos meses.
SELECT
  conjunto,
  tipo_orbita,
  COUNT(*) AS focos,
  COUNTIF(foco_intenso) AS positivos,
  ROUND(100 * COUNTIF(foco_intenso) / COUNT(*), 2) AS pct_positivos
FROM `{{DATASET}}.gold_treino`
GROUP BY conjunto, tipo_orbita
ORDER BY conjunto DESC, tipo_orbita;
