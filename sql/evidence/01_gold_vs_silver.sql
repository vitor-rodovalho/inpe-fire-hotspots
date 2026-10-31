-- Evidência: os agregados do Dataflow batem com a Silver de streaming.
-- Faz a mesma conta da gold_agregados_janela sobre a Silver (focos e focos sem
-- FRP por hora de detecção e estado) e resume as janelas em uma linha por
-- situação. O esperado é uma única linha 'ok', com o mesmo número de focos dos
-- dois lados. Para ver janela por janela, use sql/demo/04_check_aggregates.sql.
-- A gold pode ter mais de uma gravação por janela e estado; vale a mais recente.
-- Executar: bash sql/run_sql.sh sql/evidence/01_gold_vs_silver.sql

WITH silver_sem_repeticao AS (
  SELECT *
  FROM `{{DATASET}}.silver_focos_streaming`
  WHERE data_deteccao >= DATE '{{DATA_CORTE}}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ingerido_em) = 1
),
pelo_sql AS (
  SELECT
    TIMESTAMP_TRUNC(data_hora_gmt, HOUR) AS inicio_janela,
    estado,
    COUNT(*) AS focos,
    COUNTIF(frp IS NULL) AS sem_frp
  FROM silver_sem_repeticao
  GROUP BY inicio_janela, estado
),
pelo_dataflow AS (
  SELECT
    inicio_janela,
    estado,
    qtd_focos AS focos,
    qtd_sem_frp AS sem_frp,
    COUNT(*) OVER (PARTITION BY inicio_janela, estado) AS gravacoes
  FROM `{{DATASET}}.gold_agregados_janela`
  WHERE DATE(inicio_janela) >= DATE '{{DATA_CORTE}}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY inicio_janela, estado ORDER BY calculado_em DESC) = 1
)
SELECT
  CASE
    WHEN d.focos IS NULL THEN 'falta_na_gold'
    WHEN s.focos IS NULL THEN 'falta_na_silver'
    WHEN d.focos = s.focos AND d.sem_frp = s.sem_frp THEN 'ok'
    ELSE 'diferente'
  END AS situacao,
  COUNT(*) AS janelas,
  SUM(IFNULL(d.focos, 0)) AS focos_na_gold,
  SUM(IFNULL(s.focos, 0)) AS focos_na_silver,
  MAX(d.gravacoes) AS max_gravacoes_por_janela
FROM pelo_dataflow AS d
FULL OUTER JOIN pelo_sql AS s
  ON d.inicio_janela = s.inicio_janela AND d.estado = s.estado
GROUP BY situacao
ORDER BY situacao;
