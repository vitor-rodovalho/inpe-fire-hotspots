-- =============================================================================
-- Teste com carga menor: copia uma amostra da Bronze para um dataset de teste.
--
-- Serve para rodar a Silver, a view e a Gold inteiras, em segundos e por
-- centavos, antes de rodar no dataset real. A amostra tem dois meses, para
-- manter a divisão por tempo: ago/2026 (treino) e set/2026 (teste), e só um em
-- cada UM_EM_CADA focos, escolhido pelo id (a mesma amostra a cada execução).
-- As referências (satelites e limiar_frp) são copiadas inteiras do dataset real.
--
-- Só roda no modo teste. Sem DATASET_TESTE, o ASSERT abaixo para o script, para
-- que a Bronze real nunca seja substituída pela amostra.
--
-- Executar:
--   bq --location=us-central1 mk -d focos_teste        # Uma vez
--   DATASET_TESTE=focos_teste bash sql/run_sql.sh sql/teste/01_amostra_bronze.sql
-- =============================================================================

DECLARE PRIMEIRO_MES DATE DEFAULT DATE '2026-08-01';
DECLARE ULTIMO_MES DATE DEFAULT DATE '2026-09-01';
DECLARE UM_EM_CADA INT64 DEFAULT 10;   -- 10 = 10% dos focos; 1 = todos os focos dos dois meses

ASSERT '{{DATASET}}' != '{{DATASET_ORIGEM}}'
AS 'Modo teste desligado: rode com DATASET_TESTE=focos_teste, senão a Bronze real seria substituída';

CREATE OR REPLACE TABLE `{{DATASET}}.bronze_focos_mensal`
PARTITION BY DATE_TRUNC(mes_referencia, MONTH)
CLUSTER BY nome_arquivo
OPTIONS (description = 'Amostra da Bronze para testar a Frente A (sql/teste/01_amostra_bronze.sql)')
AS
SELECT *
FROM `{{DATASET_ORIGEM}}.bronze_focos_mensal`
WHERE mes_referencia BETWEEN PRIMEIRO_MES AND ULTIMO_MES
  AND MOD(ABS(FARM_FINGERPRINT(IFNULL(id, ''))), UM_EM_CADA) = 0;

-- Cópia inteira (é pequena): a classificação de órbita não deve mudar com a amostra
CREATE OR REPLACE TABLE `{{DATASET}}.satelites`
OPTIONS (description = 'Cópia de satelites para o teste da Frente A')
AS
SELECT * FROM `{{DATASET_ORIGEM}}.satelites`;

-- O limiar gravado pela Frente C (model/exploracao_limiar.py), calculado sobre
-- todos os meses de treino, e não sobre a amostra
CREATE OR REPLACE TABLE `{{DATASET}}.limiar_frp`
OPTIONS (description = 'Cópia de limiar_frp para o teste da Frente A')
AS
SELECT * FROM `{{DATASET_ORIGEM}}.limiar_frp`;

-- Resultado, para conferir
SELECT
  mes_referencia,
  COUNT(*) AS focos_na_amostra,
  COUNTIF(frp IS NULL OR TRIM(frp) = '') AS sem_frp,
  COUNT(DISTINCT TRIM(satelite)) AS satelites
FROM `{{DATASET}}.bronze_focos_mensal`
GROUP BY mes_referencia
ORDER BY mes_referencia;
