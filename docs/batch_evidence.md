# Evidências do batch

Resultados da Silver histórica, da view unificada e da Gold de treino, medidos
no GCP (projeto `inpe-fire-hotspots`, dataset `focos`) em 26/10/2026. Cada
número sai da consulta indicada ao lado (ordem de execução em
[sql/README.md](../sql/README.md)).

## Arquivos do INPE no bucket
- Tamanho total: 596,78 MiB, sendo 504,62 MiB em `raw/mensal/` (12 arquivos, out/2025 a set/2026)
  e 92,16 MiB em `raw/diario/`.
  Comando: `gsutil du -sh gs://inpe-fire-hotspots-data/raw/mensal gs://inpe-fire-hotspots-data/raw/diario`.

## Silver histórica
Nenhum foco foi descartado nem repetido: a Silver tem exatamente os 3.342.337
focos da Bronze, um por id, de 01/10/2025 a 30/09/2026 (365 dias), com o mesmo
esquema da `silver_focos_streaming`. Gerada em 26/10/2026 às 22:31 UTC.

| Verificação | Esperado | Obtido | Situação |
|---|---|---|---|
| Focos na Bronze x na Silver | 3.342.337 | 3.342.337 | ok |
| Ids distintos | 3.342.337 | 3.342.337 | ok |
| Colunas iguais às da Silver de streaming (nome, tipo, ordem) | 20 | 20 | ok |
| Focos sem FRP | 55.605 (perfil A1) | 55.605 | ok |

Contagem por mês, Bronze x Silver (`sql/silver/03_check_silver.sql`), todas `ok`:

| Mês | Focos |
|---|---|
| 2025-10 | 823.767 |
| 2025-11 | 358.921 |
| 2025-12 | 152.390 |
| 2026-01 | 86.053 |
| 2026-02 | 42.895 |
| 2026-03 | 42.954 |
| 2026-04 | 31.736 |
| 2026-05 | 82.458 |
| 2026-06 | 132.772 |
| 2026-07 | 159.934 |
| 2026-08 | 651.243 |
| 2026-09 | 777.214 |

## Particionamento
- Consulta direta na Silver sem filtro de data, recusada pelo BigQuery:
  `bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM focos.silver_focos_historico'`.
  Erro: `Cannot query over table 'focos.silver_focos_historico' without a filter over column(s)
  'data_deteccao' that can be used for partition elimination`.
- Mesma contagem por estado sobre a view, comparada pela estimativa do `DRY_RUN=1`
  (limite superior informado pelo BigQuery):

| Consulta | Filtro | Bytes estimados |
|---|---|---|
| `sql/evidence/06_bytes_one_day.sql` | 1 dia (15/08/2026) | 617.504 (603 KiB) |
| `sql/evidence/07_bytes_whole_period.sql` | nenhum (todo o período) | 129.605.023 (123,6 MiB) |

Com o filtro de um dia, a mesma consulta lê cerca de 210 vezes menos: só a
partição pedida.

## Limiar de FRP
Gravado pela Frente C (`model/exploracao_limiar.py --gravar`), percentil 90 dos
meses de treino: 202,1 MW (geoestacionário) e 28,4 MW (polar). Detalhes em
[model/README.md](../model/README.md).

## View unificada
As duas origens aparecem lado a lado, sem dia em comum: o histórico até
30/09/2026 e o streaming a partir de 01/10/2026. Fonte: `sql/demo/06_count_by_origin.sql`.

| Origem | Focos | Sem FRP | Primeiro dia | Último dia | Dias | Última ingestão (UTC) |
|---|---|---|---|---|---|---|
| batch | 3.342.337 | 55.605 | 2025-10-01 | 2026-09-30 | 365 | 2026-10-26 22:31 |
| streaming | 625.215 | 23.211 | 2026-10-01 | 2026-10-18 | 18 | 2026-10-19 12:56 |

O lado do streaming confere com o status de 19/10 (625.215 focos na Silver de
streaming, 23.211 sem FRP): a deduplicação da view não encontrou repetições.

## Gold de treino
A Gold reproduz exatamente o conjunto da etapa C2 da Frente C: 2.530.560 focos
de treino (10,0% positivos) e 756.172 de teste (10,8%). No treino, os positivos
ficam perto de 10% porque o limiar é o percentil 90 desses mesmos meses; a
diferença no teste mostra o quanto setembro foi diferente. Fonte: consulta
de leitura sobre `focos.gold_treino`.

| Conjunto | Órbita | Focos | Positivos | % positivos |
|---|---|---|---|---|
| treino | geoestacionario | 547.686 | 54.728 | 9,99 |
| treino | polar | 1.982.874 | 198.019 | 9,99 |
| teste | geoestacionario | 195.766 | 18.713 | 9,56 |
| teste | polar | 560.406 | 62.898 | 11,22 |
| **treino (total)** | | **2.530.560** | **252.747** | **10,0** |
| **teste (total)** | | **756.172** | **81.611** | **10,8** |
