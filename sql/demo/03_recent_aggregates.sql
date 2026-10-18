-- Últimas janelas de 1 hora fechadas pelo Dataflow, por estado.
-- Executar: bash sql/run_sql.sh sql/demo/03_recent_aggregates.sql

SELECT
  inicio_janela,
  fim_janela,
  estado,
  qtd_focos,
  qtd_sem_frp,
  ROUND(frp_medio, 1) AS frp_medio,
  qtd_intensos,
  calculado_em
FROM `{{DATASET}}.gold_agregados_janela`
WHERE DATE(inicio_janela) >= DATE '{{DATA_CORTE}}'
ORDER BY calculado_em DESC, qtd_focos DESC
LIMIT 30;
