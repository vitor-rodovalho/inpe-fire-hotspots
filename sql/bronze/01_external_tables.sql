-- =============================================================================
-- Bronze, passo 1: tabelas externas sobre os arquivos do bucket.
--
-- Não copiam dados: apenas permitem consultar os CSVs no Cloud Storage com SQL.
-- Todas as colunas entram como texto (STRING), do jeito que vieram do INPE.
-- A conversão de tipos é trabalho da Silver.
--
-- Executar: bash sql/run_sql.sh sql/bronze/01_external_tables.sql
-- =============================================================================

-- Os 16 campos do INPE, na ordem do arquivo.
CREATE OR REPLACE EXTERNAL TABLE `{{DATASET}}.ext_focos_mensal` (
  id STRING,
  lat STRING,
  lon STRING,
  data_hora_gmt STRING,
  satelite STRING,
  municipio STRING,
  estado STRING,
  pais STRING,
  municipio_id STRING,
  estado_id STRING,
  pais_id STRING,
  numero_dias_sem_chuva STRING,
  precipitacao STRING,
  risco_fogo STRING,
  bioma STRING,
  frp STRING
)
OPTIONS (
  format = 'CSV',
  uris = ['gs://{{BUCKET}}/{{PASTA_RAW_MENSAL}}/*.csv'],
  skip_leading_rows = 1,
  field_delimiter = ',',
  encoding = 'UTF-8',              -- se A1 mostrar acentos quebrados, trocar para 'ISO-8859-1'
  allow_quoted_newlines = TRUE,
  max_bad_records = 0              -- qualquer linha fora do formato faz a carga falhar
);

-- Manifesto gerado pelo crawler: quantas linhas cada arquivo tinha ao ser baixado
CREATE OR REPLACE EXTERNAL TABLE `{{DATASET}}.ext_manifesto` (
  uri STRING,
  tipo STRING,
  linhas INT64,
  bytes_csv INT64,
  url_origem STRING,
  baixado_em TIMESTAMP
)
OPTIONS (
  format = 'CSV',
  uris = ['gs://{{BUCKET}}/{{PASTA_MANIFESTO}}/arquivos.csv'],
  skip_leading_rows = 1
);
