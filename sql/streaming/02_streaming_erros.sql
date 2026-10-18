-- =============================================================================
-- Mensagens rejeitadas pela validação do streaming, com o motivo.
--
-- Executar: bash sql/run_sql.sh sql/streaming/02_streaming_erros.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{{DATASET}}.streaming_erros` (
  mensagem_bruta STRING OPTIONS (description = 'Corpo da mensagem como chegou'),
  atributos STRING OPTIONS (description = 'Atributos da mensagem do Pub/Sub, em JSON'),
  motivo STRING OPTIONS (description = 'Por que a mensagem foi rejeitada'),
  recebido_em TIMESTAMP
)
PARTITION BY DATE(recebido_em)
OPTIONS (description = 'Mensagens do Pub/Sub que não passaram na validação');
