-- Evidência: mensagens rejeitadas pela validação, por motivo, com um exemplo
-- de mensagem de cada. No replay, essas mensagens são cópias estragadas de
-- propósito (--fracao-invalidas). O foco original segue intacto para a Silver.
-- Executar: bash sql/run_sql.sh sql/evidence/03_errors_by_reason.sql

SELECT
  motivo,
  COUNT(*) AS mensagens,
  ANY_VALUE(mensagem_bruta) AS exemplo
FROM `{{DATASET}}.streaming_erros`
WHERE DATE(recebido_em) >= DATE '{{DATA_CORTE}}'
GROUP BY motivo
ORDER BY mensagens DESC;
