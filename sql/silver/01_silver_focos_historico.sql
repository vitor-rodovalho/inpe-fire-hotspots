-- =============================================================================
-- Silver histórica: focos limpos dos arquivos mensais (origem = 'batch').
--
-- As regras são as mesmas do streaming (pipeline/focos_stream/cleaning.py),
-- para que um foco saia igual pelos dois caminhos:
--   - apara espaços de todos os campos;
--   - vazio e -999 viram NULL em todas as colunas numéricas;
--   - descarta o que o streaming mandaria para streaming_erros: campo
--     obrigatório ausente, número ou data que não se converte, coordenada fora
--     do Brasil e risco_fogo fora de 0 a 1. O motivo usa o mesmo texto do Beam;
--   - data_deteccao = DATE(data_hora_gmt), que é a coluna de partição;
--   - remove repetições por id (o perfil mostrou que o id é único, então é só
--     uma proteção). Detecções do mesmo fogo por satélites diferentes ficam.
--
-- Mesmo esquema da silver_focos_streaming (sql/streaming/01), para que as duas
-- se unam na vw_focos_unificada. A tabela é recriada inteira: rodar de novo
-- não duplica nada e não toca na Silver de streaming.
--
-- Rodar depois da Bronze (sql/bronze/02). Ao final, mostra quantos focos
-- entraram e quantos foram descartados, por motivo.
--
-- Executar: bash sql/run_sql.sh sql/silver/01_silver_focos_historico.sql
-- =============================================================================

-- Mesmas constantes de pipeline/focos_stream/cleaning.py
DECLARE LAT_MIN FLOAT64 DEFAULT -34.0;
DECLARE LAT_MAX FLOAT64 DEFAULT 5.5;
DECLARE LON_MIN FLOAT64 DEFAULT -74.5;
DECLARE LON_MAX FLOAT64 DEFAULT -28.5;
DECLARE RISCO_FOGO_MIN FLOAT64 DEFAULT 0.0;
DECLARE RISCO_FOGO_MAX FLOAT64 DEFAULT 1.0;

-- Texto aparado; vazio vira NULL (_texto no Beam)
CREATE TEMP FUNCTION texto(x STRING) AS (NULLIF(TRIM(x), ''));

-- Texto para número; vazio e -999 viram NULL (para_float no Beam)
CREATE TEMP FUNCTION numero(x STRING) AS (
  NULLIF(SAFE_CAST(NULLIF(TRIM(x), '') AS FLOAT64), -999)
);

-- Tem texto, mas não é número (o Beam rejeita com numero_invalido)
CREATE TEMP FUNCTION nao_e_numero(x STRING) AS (
  NULLIF(TRIM(x), '') IS NOT NULL AND SAFE_CAST(TRIM(x) AS FLOAT64) IS NULL
);

-- É número, mas não é inteiro (o Beam rejeita com inteiro_invalido)
CREATE TEMP FUNCTION nao_e_inteiro(x STRING) AS (
  NULLIF(SAFE_CAST(NULLIF(TRIM(x), '') AS FLOAT64), -999)
    != TRUNC(NULLIF(SAFE_CAST(NULLIF(TRIM(x), '') AS FLOAT64), -999))
);

-- Horário do INPE (GMT), nos mesmos formatos que o Beam aceita
CREATE TEMP FUNCTION data_hora(x STRING) AS (
  COALESCE(
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', TRIM(x)),
    SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', TRIM(x)),
    SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%S', TRIM(x)),
    SAFE.PARSE_TIMESTAMP('%Y/%m/%d %H:%M:%S', TRIM(x))
  )
);

-- Passo 1: cada linha da Bronze tipada, com o motivo de descarte (ou NULL)
CREATE TEMP TABLE convertido AS
SELECT
  texto(id) AS id,
  numero(lat) AS lat,
  numero(lon) AS lon,
  data_hora(data_hora_gmt) AS data_hora_gmt,
  texto(satelite) AS satelite,
  texto(municipio) AS municipio,
  texto(estado) AS estado,
  texto(pais) AS pais,
  -- SAFE_CAST: um valor não inteiro é descartado abaixo, mas não pode quebrar a carga
  SAFE_CAST(numero(municipio_id) AS INT64) AS municipio_id,
  SAFE_CAST(numero(estado_id) AS INT64) AS estado_id,
  SAFE_CAST(numero(pais_id) AS INT64) AS pais_id,
  numero(numero_dias_sem_chuva) AS numero_dias_sem_chuva,
  numero(precipitacao) AS precipitacao,
  numero(risco_fogo) AS risco_fogo,
  texto(bioma) AS bioma,
  numero(frp) AS frp,
  nome_arquivo,
  -- Mesma ordem de verificação de validar() em cleaning.py
  CASE
    WHEN texto(id) IS NULL THEN 'campo_obrigatorio_ausente:id'
    WHEN texto(lat) IS NULL THEN 'campo_obrigatorio_ausente:lat'
    WHEN texto(lon) IS NULL THEN 'campo_obrigatorio_ausente:lon'
    WHEN texto(data_hora_gmt) IS NULL THEN 'campo_obrigatorio_ausente:data_hora_gmt'
    WHEN texto(satelite) IS NULL THEN 'campo_obrigatorio_ausente:satelite'
    WHEN texto(estado) IS NULL THEN 'campo_obrigatorio_ausente:estado'
    WHEN nao_e_numero(lat) THEN 'numero_invalido:lat'
    WHEN nao_e_numero(lon) THEN 'numero_invalido:lon'
    WHEN nao_e_numero(numero_dias_sem_chuva) THEN 'numero_invalido:numero_dias_sem_chuva'
    WHEN nao_e_numero(precipitacao) THEN 'numero_invalido:precipitacao'
    WHEN nao_e_numero(risco_fogo) THEN 'numero_invalido:risco_fogo'
    WHEN nao_e_numero(frp) THEN 'numero_invalido:frp'
    WHEN nao_e_numero(municipio_id) THEN 'numero_invalido:municipio_id'
    WHEN nao_e_inteiro(municipio_id) THEN 'inteiro_invalido:municipio_id'
    WHEN nao_e_numero(estado_id) THEN 'numero_invalido:estado_id'
    WHEN nao_e_inteiro(estado_id) THEN 'inteiro_invalido:estado_id'
    WHEN nao_e_numero(pais_id) THEN 'numero_invalido:pais_id'
    WHEN nao_e_inteiro(pais_id) THEN 'inteiro_invalido:pais_id'
    WHEN data_hora(data_hora_gmt) IS NULL THEN 'data_hora_invalida'
    WHEN numero(lat) IS NULL OR numero(lon) IS NULL THEN 'coordenada_ausente'
    WHEN NOT (numero(lat) BETWEEN LAT_MIN AND LAT_MAX AND numero(lon) BETWEEN LON_MIN AND LON_MAX)
      THEN 'coordenada_fora_do_brasil'
    WHEN numero(risco_fogo) IS NOT NULL AND NOT (numero(risco_fogo) BETWEEN RISCO_FOGO_MIN AND RISCO_FOGO_MAX)
      THEN 'risco_fogo_fora_da_faixa'
    -- Só no batch: dias a partir do corte pertencem ao streaming
    WHEN DATE(data_hora(data_hora_gmt)) >= DATE '{{DATA_CORTE}}' THEN 'depois_da_data_corte'
  END AS motivo_descarte
FROM `{{DATASET}}.bronze_focos_mensal`;

-- Passo 2: a tabela, com o mesmo esquema da silver_focos_streaming
CREATE OR REPLACE TABLE `{{DATASET}}.silver_focos_historico` (
  id STRING,
  lat FLOAT64,
  lon FLOAT64,
  data_hora_gmt TIMESTAMP,
  satelite STRING,
  municipio STRING,
  estado STRING,
  pais STRING,
  municipio_id INT64,
  estado_id INT64,
  pais_id INT64,
  numero_dias_sem_chuva FLOAT64,
  precipitacao FLOAT64,
  risco_fogo FLOAT64,
  bioma STRING,
  frp FLOAT64 OPTIONS (description = 'Vazio e -999 viram NULL'),
  data_deteccao DATE OPTIONS (description = 'DATE(data_hora_gmt), coluna de partição'),
  origem STRING OPTIONS (description = 'batch ou streaming'),
  publicado_em TIMESTAMP OPTIONS (description = 'Instante em que o replay publicou no Pub/Sub'),
  ingerido_em TIMESTAMP OPTIONS (description = 'Instante em que o Dataflow processou o foco')
)
PARTITION BY data_deteccao
CLUSTER BY estado, satelite
OPTIONS (
  require_partition_filter = TRUE,
  description = 'Focos limpos vindos dos arquivos mensais (Bronze -> SQL)'
);

-- Passo 3: só as linhas válidas, sem repetição de id
INSERT INTO `{{DATASET}}.silver_focos_historico`
SELECT
  id, lat, lon, data_hora_gmt, satelite, municipio, estado, pais,
  municipio_id, estado_id, pais_id,
  numero_dias_sem_chuva, precipitacao, risco_fogo, bioma, frp,
  DATE(data_hora_gmt) AS data_deteccao,
  'batch' AS origem,
  CAST(NULL AS TIMESTAMP) AS publicado_em,  -- Só existe no streaming
  CURRENT_TIMESTAMP() AS ingerido_em
FROM convertido
WHERE motivo_descarte IS NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY nome_arquivo) = 1;

-- Resultado, para conferir: bronze = silver + descartes + repetidos
WITH na_silver AS (
  SELECT COUNT(*) AS focos
  FROM `{{DATASET}}.silver_focos_historico`
  WHERE data_deteccao < DATE '{{DATA_CORTE}}'
),
aceitos AS (
  SELECT COUNT(*) AS focos FROM convertido WHERE motivo_descarte IS NULL
)
SELECT 1 AS ordem, 'bronze' AS etapa, CAST(NULL AS STRING) AS motivo, COUNT(*) AS focos
FROM convertido
UNION ALL
SELECT 2, 'descartado', motivo_descarte, COUNT(*)
FROM convertido
WHERE motivo_descarte IS NOT NULL
GROUP BY motivo_descarte
UNION ALL
SELECT 3, 'repetido_por_id', NULL, aceitos.focos - na_silver.focos
FROM aceitos, na_silver
UNION ALL
SELECT 4, 'silver', NULL, focos
FROM na_silver
ORDER BY ordem, focos DESC;
