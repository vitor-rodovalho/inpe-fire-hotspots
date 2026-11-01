# Focos de calor do INPE: arquitetura Batch + Streaming na GCP

Trabalho 2 de Processamento de Dados Massivos. Dado um foco de calor detectado
por satélite, estimamos a probabilidade de ele ser intenso (FRP alto), com
base no que se sabe no momento da detecção.

**O batch ensina, o streaming aplica, avalia e agrega.**

- **Batch:** arquivos mensais do INPE (out/2025 a set/2026) passam por Bronze,
  Silver e Gold no BigQuery e treinam o modelo.
- **Streaming:** arquivos diários a partir de 01/10/2026 são publicados foco a
  foco no Pub/Sub; o Dataflow valida, limpa, grava e agrega em janelas de 1 hora.
- **Modelo e API:** classificador do BigQuery ML registrado no Vertex AI e
  servido por uma API REST no Cloud Run.

**API no ar:** `https://api-foco-intenso-XXXXXXXX.us-central1.run.app`
([documentação interativa](https://api-foco-intenso-XXXXXXXX.us-central1.run.app/docs)).
Evidências de paridade e latência em [docs/api_evidence.md](docs/api_evidence.md).

## Arquitetura

```
                       INPE (arquivos CSV)
              ┌───────────────┴────────────────┐
      mensais: out/2025 a set/2026     diários: a partir de 01/10/2026
              │  BATCH                         │  STREAMING
     Cloud Storage → Bronze             replay → Pub/Sub (focos-replay)
              │                                │
     Silver histórica                   Dataflow: valida, limpa, deduplica
     (origem = 'batch')                  ├→ Silver de streaming (origem = 'streaming')
              │                          ├→ streaming_erros
              │                          └→ gold_agregados_janela (janelas de 1 h)
              └──────────┬──────────────────────┘
               vw_focos_unificada (corte em DATA_CORTE)
                         │
               gold_treino → CREATE MODEL (BigQuery ML) → Vertex AI Model Registry
                                     │
                         EXPORT MODEL → gs://.../modelos/foco_intenso/v1/
                                     │
                         API no Cloud Run: POST /predict, GET /health
```

Todas as tabelas ficam no dataset `focos`, em `us-central1`, particionadas
por dia da detecção com filtro obrigatório. Os nomes de tudo estão em
[docs/contracts.md](docs/contracts.md).

## Estrutura do repositório

```
README.md                  # Arquitetura, como rodar cada peça e link do Cloud Run
config.env                 # Todas as constantes do projeto (nomes, região, períodos)
config.local.env.example   # Modelo para valores pessoais (faturamento, e-mails)
infra/                     # Projeto, APIs, orçamento, bucket, dataset, contas, Pub/Sub
ingestion/                 # Download do INPE para o bucket e replay para o Pub/Sub
sql/
  run_sql.sh               # Roda arquivos .sql trocando {{MARCADORES}} por config.env
  bronze/                  # Tabelas externas, carga e conferência da Bronze
  silver/                  # silver_focos_historico e vw_focos_unificada
  reference/               # Satelites e limiar_frp
  streaming/               # Tabelas gravadas pelo Dataflow
  gold/                    # gold_treino, vw_previsoes, vw_monitoramento
  modelo/                  # CREATE MODEL, ML.EVALUATE, EXPORT MODEL
  demo/                    # Consultas usadas na demonstração
  evidence/                # Evidências do streaming (notebook 02)
pipeline/                  # Apache Beam / Dataflow
model/                     # Exploração, export e arquivo de paridade
api/                       # FastAPI, Dockerfile, requirements.txt, deploy.sh, testes
scripts/                   # demo.py (chamadas à API na apresentação)
notebooks/                 # Exploração e evidências; não roda nada em produção
docs/                      # contracts.md, diagrama, perfil dos dados, figuras e evidências
```


## Configuração

Tudo que é alterado de um ambiente para outro está em `config.env`. Para reproduzir
em outra conta GCP:

1. Edite `config.env`: no mínimo `PROJECT_ID`, que deve ser único no
   mundo. O bucket (`${PROJECT_ID}-data`) e o orçamento seguem o ID sozinhos.
2. Crie o arquivo pessoal, que não vai para o GitHub:
   ```bash
   cp config.local.env.example config.local.env
   # preencha BILLING_ACCOUNT_ID (gcloud billing accounts list) e EMAILS_EQUIPE
   ```

Os scripts `.sh` carregam os dois arquivos automaticamente. Para usar as variáveis no
terminal: `set -a; source config.env; set +a`.

## Passo a passo

Recomendado executar no **Cloud Shell**, que possui `gcloud`, `bq` e Python.

```bash
# 1. Ambiente: projeto, APIs, orçamento, bucket, dataset, contas de serviço, Pub/Sub
bash infra/00_setup_all.sh
bash infra/08_test_pubsub.sh

# 2. Tabelas de streaming
bash sql/run_sql.sh sql/streaming/*.sql

# 3. Dados do INPE no bucket, Bronze e tabelas de referência
python3 -m venv .venv && source .venv/bin/activate
pip install -r ingestion/requirements.txt
bash ingestion/run.sh download_inpe
bash sql/run_sql.sh sql/bronze/01_external_tables.sql sql/bronze/02_bronze_focos_mensal.sql
bash sql/run_sql.sh sql/bronze/03_check_bronze.sql
bash sql/run_sql.sh sql/reference/*.sql              # Orbitas geradas da Bronze e limiar vazio
bash sql/run_sql.sh sql/bronze/04_data_profile.sql   # Versão rápida, só texto
# Versão completa, com gráficos e resumo: notebooks/01_data_profile.ipynb

# 4. Pipeline de streaming: veja pipeline/README.md

# 5. Replay dos diários para o Pub/Sub (com o job do Dataflow ligado)
bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fim 2026-10-03

# 6. Evidências do streaming (depois do replay)
bash sql/run_sql.sh sql/evidence/*.sql               # Versão rápida, só texto
# Versão completa, com gráficos e resumo: notebooks/02_streaming_evidence.ipynb

# 7. Silver histórica, Gold de treino e modelo: veja sql/README.md e model/README.md

# 8. API no Cloud Run, com o modelo real: export, paridade, deploy e testes (centavos)
bash api/subir_api.sh                                # veja api/README.md
python3 scripts/demo.py                              # as três chamadas da apresentação
```

Cada script de `infra/` pode ser executado novamente sem efeito colateral.

### Teste local

O download, o replay e o pipeline também executam só na máquina (WSL, Linux, Mac
ou Cloud Shell), gravando tudo na pasta `dados/`, que não vai para o Git. Não
precisa de conta GCP e não deixa nada no bucket, no Pub/Sub ou no BigQuery.
Passo a passo em [ingestion/README.md](ingestion/README.md#teste-sem-nuvem).

## Custos e cuidados

| Item | Quando gasta | Como desativar |
|---|---|---|
| Dataflow | Enquanto o job estiver ativo (cerca de US$ 0,20 a 0,30/h) | `bash pipeline/drain.sh` |
| Cloud Run | Por requisição (dentro da cota gratuita). 1 instância mínima só no dia da apresentação | `bash api/instancias_minimas.sh 0` |
| BigQuery | Por bytes lidos. Tabelas particionadas com filtro obrigatório | Usar `DRY_RUN=1` antes de consultas massivas |
| Cloud Storage | Alguns GB de CSV | Apagar `raw/` depois da entrega |

O orçamento (`infra/03_budget.sh`) avisa por e-mail em 50%, 90% e 100% de
`ORCAMENTO_USD`, mas **não desativa nada sozinho**.

No dia da apresentação, siga [docs/checklist_apresentacao.md](docs/checklist_apresentacao.md):
o que ligar antes, o que mostrar e o que desligar depois.
