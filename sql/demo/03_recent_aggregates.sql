-- Últimas janelas de 1 hora gravadas pelo Dataflow, por estado.
-- Uma janela e estado pode ter mais de uma linha, porque o Dataflow grava o
-- total de novo quando chegam focos atrasados. Aqui fica só a mais recente.
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
QUALIFY ROW_NUMBER() OVER (PARTITION BY inicio_janela, estado ORDER BY calculado_em DESC) = 1
ORDER BY calculado_em DESC, qtd_focos DESC
LIMIT 30;
