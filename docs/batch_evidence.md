# Evidências do batch

Resultados da Silver histórica, do limiar, da view unificada e da Gold de
treino. Cada número sai da consulta indicada ao lado (ordem em
[sql/README.md](../sql/README.md)). Os campos `(preencher)` são completados
depois de rodar os SQL no projeto.

## Arquivos do INPE no bucket
- Tamanho total: `(preencher)` em `raw/mensal/` e `(preencher)` em `raw/diario/`.
  Comando: `gsutil du -sh gs://inpe-fire-hotspots-data/raw/mensal gs://inpe-fire-hotspots-data/raw/diario`.

## Silver histórica
Fonte: o resumo final de `sql/silver/01_silver_focos_historico.sql` e a conferência de `sql/silver/03_check_silver.sql`.
- Bronze: 3.342.337 focos.
- Descartados: `(preencher)`, por motivo: `(preencher)`.
- Repetidos por id: `(preencher)`.
- Silver histórica: `(preencher)` focos, de 01/10/2025 a 30/09/2026.
- Esquema igual ao da `silver_focos_streaming`: `(preencher: ok/diferente)`.

## Particionamento
- Consulta direta na Silver sem filtro de data, recusada pelo BigQuery:
  `bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM focos.silver_focos_historico'`.
  Erro: `(preencher)`.
- Mesma contagem por estado sobre a view, comparada pela estimativa do `DRY_RUN=1`:

| Consulta | Filtro | Bytes estimados |
|---|---|---|
| `sql/evidence/06_bytes_one_day.sql` | 1 dia (15/08/2026) | `(preencher)` |
| `sql/evidence/07_bytes_whole_period.sql` | nenhum (todo o período) | `(preencher)` |

## Limiar de FRP
Gravado pela Frente C (`model/exploracao_limiar.py --gravar`), percentil 90 dos
meses de treino: 202,1 MW (geoestacionário) e 28,4 MW (polar). Detalhes em
[model/README.md](../model/README.md).

## View unificada
Fonte: `sql/demo/06_count_by_origin.sql`.

| Origem | Focos | Primeiro dia | Último dia |
|---|---|---|---|
| batch | `(preencher)` | `(preencher)` | `(preencher)` |
| streaming | `(preencher)` | `(preencher)` | `(preencher)` |

## Gold de treino
Fonte: o resumo final de `sql/gold/01_gold_treino.sql`.

| Conjunto | Órbita | Focos | Positivos | % positivos |
|---|---|---|---|---|
| treino | geoestacionario | `(preencher)` | `(preencher)` | `(preencher)` |
| treino | polar | `(preencher)` | `(preencher)` | `(preencher)` |
| teste | geoestacionario | `(preencher)` | `(preencher)` | `(preencher)` |
| teste | polar | `(preencher)` | `(preencher)` | `(preencher)` |

No total, o esperado é o mesmo da etapa C2 da Frente C: 2.530.560 focos de
treino (10,0% positivos) e 756.172 de teste (10,8%). No treino, os positivos
ficam perto de 10% porque o limiar é o percentil 90 desses mesmos meses; a
diferença no teste mostra o quanto setembro foi diferente.
