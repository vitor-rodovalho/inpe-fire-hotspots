# SQL

Tudo o que roda no BigQuery, no dataset `focos`. Cada pasta é uma camada, e os
arquivos são numerados pela ordem de execução. Todos rodam com `run_sql.sh`,
que troca os marcadores (`{{DATASET}}`, `{{DATA_CORTE}}`...) pelos valores de
`config.env`:

```bash
bash sql/run_sql.sh sql/silver/01_silver_focos_historico.sql
SOMENTE_MOSTRAR=1 bash sql/run_sql.sh arquivo.sql   # Imprime o SQL final, sem rodar
DRY_RUN=1 bash sql/run_sql.sh arquivo.sql           # Estima os bytes lidos, sem rodar
```

Os arquivos que criam tabelas terminam com uma consulta de conferência.


## Ordem de execução

| # | Arquivo | Cria | Depende de | Quem consome |
|---|---|---|---|---|
| 1 | `bronze/01_external_tables.sql` | `ext_focos_mensal`, `ext_manifesto` (externas) | CSVs no bucket | Bronze |
| 2 | `bronze/02_bronze_focos_mensal.sql` | `bronze_focos_mensal` | 1 | Silver, `satelites` |
| 3 | `bronze/03_check_bronze.sql` | (conferência contra o manifesto) | 2 | - |
| 4 | `reference/01_satelites.sql` | `satelites` | 2 | Gold, limiar, Dataflow, API |
| 5 | `reference/02_limiar_frp.sql` | `limiar_frp` vazia | - | Dataflow |
| 6 | `streaming/01` a `03` | `silver_focos_streaming`, `streaming_erros`, `gold_agregados_janela` | - | Dataflow grava |
| 7 | `silver/01_silver_focos_historico.sql` | `silver_focos_historico` | 2 | View, limiar |
| 8 | `reference/03_calcular_limiar_frp.sql` | preenche `limiar_frp` | 4, 5, 7 | Gold, Dataflow |
| 9 | `silver/02_vw_focos_unificada.sql` | `vw_focos_unificada` (view) | 6, 7 | Gold, demo, previsões |
| 10 | `gold/01_gold_treino.sql` | `gold_treino` | 4, 8, 9 | Modelo (Frente C) |
| 11 | `silver/03_check_silver.sql` | (conferência) | 7 | - |

```bash
bash sql/run_sql.sh sql/bronze/01_external_tables.sql sql/bronze/02_bronze_focos_mensal.sql sql/bronze/03_check_bronze.sql
bash sql/run_sql.sh sql/reference/01_satelites.sql sql/reference/02_limiar_frp.sql
bash sql/run_sql.sh sql/streaming/*.sql
bash sql/run_sql.sh sql/silver/01_silver_focos_historico.sql
bash sql/run_sql.sh sql/reference/03_calcular_limiar_frp.sql
bash sql/run_sql.sh sql/silver/02_vw_focos_unificada.sql
bash sql/run_sql.sh sql/gold/01_gold_treino.sql
bash sql/run_sql.sh sql/silver/03_check_silver.sql
```

Depois de mudar `satelites` ou `limiar_frp`, reinicie o job do Dataflow
(`pipeline/drain.sh` e `pipeline/deploy.sh`), que lê as duas ao subir. Depois
de mudar o limiar, recrie também a Gold de treino.

Rodar de novo é seguro. A Bronze, a Silver histórica, as referências e a Gold
são recriadas inteiras, e as tabelas do streaming usam `CREATE TABLE IF NOT
EXISTS`, então nunca perdem o que o Dataflow gravou.


## Camadas

**Bronze (`bronze/`).** Os CSVs mensais como vieram, tudo como texto, com o
nome do arquivo e o instante da carga. Nada é corrigido aqui.
`04_data_profile.sql` é o teste de dados (A1).

**Silver (`silver/`, `streaming/`).** Duas tabelas com o mesmo esquema: as 16
colunas do INPE tipadas, mais `data_deteccao`, `origem`, `publicado_em` e
`ingerido_em`. As duas são particionadas por `data_deteccao`, com filtro
obrigatório. A histórica é escrita por este SQL, e a de streaming pelo Dataflow.
As regras de limpeza são as mesmas nas duas (veja `docs/contracts.md`), e os
motivos de descarte do SQL usam os mesmos textos do Beam.

A `vw_focos_unificada` junta as duas pela data de corte (`DATA_CORTE`):
histórico antes, streaming a partir dela. Ela deduplica de novo o lado do
streaming, porque o Pub/Sub pode repetir mensagens. Um filtro de data na view
chega às partições das duas tabelas.

**Referências (`reference/`).** `satelites` (satélite para tipo de órbita,
calculada da Bronze) e `limiar_frp` (percentil 90 do FRP por órbita nos meses
de treino).

**Gold (`gold/`, `streaming/03`).** `gold_treino` tem as variáveis do modelo, o
rótulo `foco_intenso` e o `conjunto` (treino de out/2025 a ago/2026, teste em
set/2026). As variáveis são calculadas como na API (`api/app/features.py`).
`gold_agregados_janela` é gravada pelo Dataflow, e para ler é preciso ficar com
a gravação mais recente de cada janela (veja `docs/contracts.md`).


## Consultas da demo e evidências

| Pasta | Arquivo | Mostra |
|---|---|---|
| `demo/` | `01` a `05` | Streaming: focos por minuto, latência, agregados, conferência da Gold e erros |
| `demo/` | `06_count_by_origin.sql` | Focos por origem na view unificada |
| `evidence/` | `01` a `05` | Evidências do streaming (notebook 02) |
| `evidence/` | `06_bytes_one_day.sql`, `07_bytes_whole_period.sql` | Bytes lidos com e sem filtro de data (rodar com `DRY_RUN=1`) |

Os resultados do batch ficam em [docs/batch_evidence.md](../docs/batch_evidence.md).
