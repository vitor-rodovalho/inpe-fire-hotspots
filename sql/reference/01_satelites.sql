-- =============================================================================
-- Referência: satélite para tipo de órbita, gerada a partir da Bronze.
--
-- A mesma tabela é usada no SQL, no pipeline de streaming (qual limiar vale para
-- cada foco) e na API.
--
-- Nenhum nome é escrito à mão. A lista de satélites é a que aparece na Bronze,
-- e a órbita sai do padrão de horários das detecções:
--   - Um satélite geoestacionário fica parado sobre o mesmo ponto e manda
--     imagem o dia todo, então detecta focos em muitas horas do mesmo dia;
--   - Um polar só passa sobre o Brasil algumas vezes por dia, então detecta
--     focos em poucas horas.
--
-- Regra: no dia em que o satélite detectou focos em mais horas (UTC)
-- diferentes, se foram HORAS_MINIMAS_GEOESTACIONARIO ou mais, ele é
-- geoestacionário; senão, polar.
--
-- Colunas:
--   satelite           Nome exatamente como aparece no CSV do INPE
--   tipo_orbita        Geoestacionario ou polar
--   max_horas_num_dia  Horas diferentes com focos no dia de maior atividade
--   dias_com_focos     Quantos dias o satélite aparece na Bronze
--   primeiro_dia       Primeira detecção do satélite na Bronze
--   ultimo_dia         Última detecção do satélite na Bronze
--   gerado_em          Instante em que esta tabela foi gerada
--
-- Rodar depois de carregar a Bronze (sql/bronze/02_bronze_focos_mensal.sql) e
-- de novo sempre que a Bronze mudar. A tabela é recriada inteira. Depois,
-- reinicie o job do Dataflow, que lê esta tabela ao subir.
--
-- Executar: bash sql/run_sql.sh sql/reference/01_satelites.sql
-- =============================================================================

DECLARE HORAS_MINIMAS_GEOESTACIONARIO INT64 DEFAULT 12;

CREATE OR REPLACE TABLE `{{DATASET}}.satelites`
OPTIONS (description = 'Satélite do INPE para tipo de órbita, gerada da Bronze por sql/reference/01_satelites.sql')
AS
WITH deteccoes AS (
  SELECT
    TRIM(satelite) AS satelite,
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', TRIM(data_hora_gmt)) AS instante
  FROM `{{DATASET}}.bronze_focos_mensal`
  WHERE TRIM(IFNULL(satelite, '')) != ''
),
horas_por_dia AS (
  SELECT
    satelite,
    DATE(instante) AS dia,
    COUNT(DISTINCT EXTRACT(HOUR FROM instante)) AS horas_com_focos
  FROM deteccoes
  WHERE instante IS NOT NULL
  GROUP BY satelite, dia
)
SELECT
  satelite,
  IF(MAX(horas_com_focos) >= HORAS_MINIMAS_GEOESTACIONARIO, 'geoestacionario', 'polar') AS tipo_orbita,
  MAX(horas_com_focos) AS max_horas_num_dia,
  COUNT(*) AS dias_com_focos,
  MIN(dia) AS primeiro_dia,
  MAX(dia) AS ultimo_dia,
  CURRENT_TIMESTAMP() AS gerado_em
FROM horas_por_dia
GROUP BY satelite;

-- Resultado, para conferir a classificação
SELECT satelite, tipo_orbita, max_horas_num_dia, dias_com_focos, primeiro_dia, ultimo_dia
FROM `{{DATASET}}.satelites`
ORDER BY max_horas_num_dia DESC, satelite;
