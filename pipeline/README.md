# Pipeline de streaming

Consome os focos publicados no Pub/Sub, limpa, grava e agrega enquanto eles
chegam. Apache Beam, executado no Dataflow.

```
Pub/Sub (focos-replay-dataflow)
  └─ LerPubSub (tempo do evento = atributo ts_evento)
      └─ Validar ──────────────── inválidos ──> streaming_erros
          └─ Limpar (vazio e -999 -> nulo, tipos, data_deteccao)
              └─ Deduplicar por id (10 min)
                  ├─ GravarSilver ─────────────> silver_focos_streaming
                  └─ Janela1h (pelo horário da detecção)
                      └─ ChavePorEstado - Agregar - LinhaDaJanela
                          └─ GravarAgregados ──> gold_agregados_janela
```


## Organização

| Arquivo | O que tem |
|---|---|
| `main.py` | O grafo do pipeline e as opções de linha de comando |
| `focos_stream/cleaning.py` | Validação e limpeza (Python puro, testável) |
| `focos_stream/aggregation.py` | Contas de cada janela (Python puro, testável) |
| `focos_stream/beam_transforms.py` | DoFns e CombineFn que adaptam as funções acima ao Beam |
| `focos_stream/references.py` | Leitura de `satelites` e `limiar_frp` |
| `tests/` | Testes com pytest |
| `run_local.sh`, `deploy.sh`, `drain.sh` | Rodar na máquina (com ou sem nuvem), subir e encerrar no Dataflow |

Todas as constantes ficam no topo de cada arquivo e leem os valores de
`config.env` na raiz do repositório. Quem publica as mensagens no Pub/Sub
fica em `ingestion/`.


## Por que as janelas usam o horário da detecção

O replay acelera o tempo. Uma janela pelo horário de chegada misturaria horas
diferentes de detecção e não significaria nada. Com o horário da detecção
(atributo `ts_evento`), uma janela é uma hora real de fogo, a qualquer
velocidade de replay.

Consequência: o replay não pode voltar no tempo com o job ligado. Focos com
horário anterior a uma janela já fechada chegam "atrasados" e o Beam os descarta
dos agregados (na Silver eles entram normalmente). Antes de cada ensaio,
reinicie o job (`drain.sh` e `deploy.sh`).


## Como rodar

Há três jeitos, do mais seguro ao real:

| Modo | Lê de | Grava em | Comando |
|---|---|---|---|
| Sem nuvem | `dados/mensagens.jsonl` | `dados/pipeline/*.jsonl` | `bash pipeline/run_local.sh --offline` |
| Na máquina | Assinatura real do Pub/Sub | Tabelas reais do BigQuery | `bash pipeline/run_local.sh` |
| Dataflow | Assinatura real do Pub/Sub | Tabelas reais do BigQuery | `bash pipeline/deploy.sh` |

O modo sem nuvem roda em lote, mas passa pelas mesmas etapas (validação,
limpeza, deduplicação e janelas pelo horário da detecção). É o lugar para
testar mudanças no código sem deixar focos de teste nas tabelas. O passo a
passo, do download ao resultado, está em
[ingestion/README.md](../ingestion/README.md#teste-sem-nuvem).

Os outros dois modos precisam do ambiente criado (`infra/`), das tabelas de
`sql/streaming/` e das de `sql/reference/`, que são geradas depois da carga da
Bronze. Recomendado rodar no Cloud Shell.

```bash
# 1. Ambiente Python (uma vez)
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements-dev.txt

# 2. Testes das regras de validação, limpeza e agregação
cd pipeline && python -m pytest -q && cd ..

# 3. Rodar na máquina (DirectRunner), lendo o Pub/Sub e gravando no BigQuery reais
bash pipeline/run_local.sh
# Para testar sem as tabelas de referência no BigQuery:
#    bash pipeline/run_local.sh --referencias references_example.json
# (os satélites desse JSON são os dos CSVs reais de agosto e setembro de
# 2026. Os limiares são fictícios, só para teste)

# 4. Em outro terminal, publicar focos de teste (5% propositalmente inválidos)
pip install -r ingestion/requirements.txt
bash ingestion/run.sh replay_pubsub --inicio 2026-09-30 \
  --max-mensagens 200 --intervalo-fixo 0.1 --fracao-invalidas 0.05

# 5. Conferir
bash sql/run_sql.sh sql/demo/01_streaming_per_minute.sql sql/demo/05_errors_by_reason.sql

# 6. Subir no Dataflow e, ao terminar, encerrar
bash pipeline/deploy.sh
bash pipeline/drain.sh
```


## Custo

O job usa 1 worker `n1-standard-2` com Streaming Engine e disco de 30 GB,
algo como US$ 0,20 a 0,30 por hora ligado (estimativa pela tabela de preços do
Dataflow, a confirmar no teste de 30 minutos). Ligue só nos testes, nos ensaios e
no dia, e sempre termine com `drain.sh`.


## Consultas de conferência

Em `sql/demo/`:

- `01_streaming_per_minute.sql`: focos gravados por minuto de ingestão.
- `02_streaming_latency.sql`: latência `publicado_em -> ingerido_em`.
- `03_recent_aggregates.sql`: últimas janelas fechadas.
- `04_check_aggregates.sql`: agregados do Dataflow contra a mesma conta em SQL.
- `05_errors_by_reason.sql`: mensagens rejeitadas por motivo.
