-- Mensagens rejeitadas pelo streaming, por motivo.
-- Executar: bash sql/run_sql.sh sql/demo/05_errors_by_reason.sql

SELECT
  motivo,
  COUNT(*) AS mensagens,
  MAX(recebido_em) AS ultima
FROM `{{DATASET}}.streaming_erros`
WHERE DATE(recebido_em) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY motivo
ORDER BY mensagens DESC;
