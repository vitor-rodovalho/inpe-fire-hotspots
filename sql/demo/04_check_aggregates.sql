-- Confere os agregados do Dataflow contra a mesma conta feita em SQL sobre a
-- Silver de streaming. "situacao" = 'ok' quando batem.
-- Só compara janelas que o Dataflow já gravou, pela linha mais recente de cada
-- janela e estado (o total é gravado de novo quando chegam focos atrasados).
-- Executar: bash sql/run_sql.sh sql/demo/04_check_aggregates.sql

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
    COUNT(*) AS qtd_focos_sql,
    COUNTIF(frp IS NULL) AS qtd_sem_frp_sql
  FROM silver_sem_repeticao
  GROUP BY inicio_janela, estado
),
pelo_dataflow AS (
  SELECT inicio_janela, estado, qtd_focos, qtd_sem_frp
  FROM `{{DATASET}}.gold_agregados_janela`
  WHERE DATE(inicio_janela) >= DATE '{{DATA_CORTE}}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY inicio_janela, estado ORDER BY calculado_em DESC) = 1
)
SELECT
  d.inicio_janela,
  d.estado,
  d.qtd_focos,
  s.qtd_focos_sql,
  d.qtd_sem_frp,
  s.qtd_sem_frp_sql,
  IF(d.qtd_focos = s.qtd_focos_sql AND d.qtd_sem_frp = s.qtd_sem_frp_sql, 'ok', 'diferente') AS situacao
FROM pelo_dataflow AS d
LEFT JOIN pelo_sql AS s USING (inicio_janela, estado)
ORDER BY d.inicio_janela DESC, d.estado;
