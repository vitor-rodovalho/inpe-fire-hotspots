# API foco intenso (Frente D)

API REST que recebe um foco de calor, real ou hipotético, e devolve a
probabilidade de ele ser intenso. Roda em FastAPI e vai para o Cloud Run
como `api-foco-intenso`.

```
POST /predict  {"satelite": "NOAA-20", "data_hora_gmt": "2026-10-14T18:42:00Z", ...}
            -> {"probabilidade_intenso": 0.7132, "intenso": true, "versao_modelo": "..."}
GET  /health   {"status": "ok", "versao_modelo": "..."}
GET  /docs     Documentação interativa (gerada pelo FastAPI)
```

Toda resposta traz o cabeçalho `X-Tempo-Processamento-Ms`, o tempo gasto
dentro da API, sem a rede.

## Estrutura

```
app/
  main.py      Rotas e carregamento do modelo quando o contêiner sobe
  schemas.py   Contrato: campos, tipos e faixas válidas (fora delas, 422)
  features.py  Entrada -> variáveis do modelo, calculadas como na Gold
  modelo.py    Lê o pacote do modelo (pasta local ou gs://) e calcula a probabilidade
  config.py    Variáveis de ambiente
modelo_provisorio/
  treinar.py   Modelo provisório, com dados sintéticos, para testar a API antes do real
tests/         pytest, sem nuvem
```

Cada módulo tem uma responsabilidade. Para trocar o modelo provisório pelo
real, muda só o pacote; a codificação das variáveis fica no `manifest.json`.

## Contrato

| Campo | Tipo | Regra |
|---|---|---|
| `satelite` | texto | Precisa estar na tabela `satelites` (senão 422) |
| `data_hora_gmt` | data e hora | ISO 8601 ou o formato do INPE (`2026-10-14 18:42:00`); sem fuso, é GMT |
| `lat`, `lon` | número | Dentro do retângulo do Brasil (o mesmo do pipeline) |
| `bioma` | texto | Um dos seis biomas do INPE |
| `numero_dias_sem_chuva` | número, opcional | `>= 0`; vazio ou `-999` vira nulo |
| `precipitacao` | número, opcional | `>= 0`; vazio ou `-999` vira nulo |
| `risco_fogo` | número, opcional | De 0 a 1; vazio ou `-999` vira nulo |

O FRP não entra: é o que o modelo estima. Campos a mais são ignorados, então
uma linha da Silver pode ser enviada como está.

## Pacote do modelo

Uma pasta, local ou no bucket, com três arquivos:

| Arquivo | Conteúdo |
|---|---|
| `manifest.json` | `versao_modelo`, `arquivo_modelo`, `limiar_decisao` e a lista ordenada de variáveis, com as categorias das categóricas |
| `satelites.json` | Satélite para tipo de órbita, no formato de `pipeline/references_example.json` |
| `model.json` | Booster do XGBoost (o nome vem do manifest) |

A variável de ambiente `MODELO_URI` diz onde ele está (padrão: `modelo_local/`).

## Rodar na máquina

```bash
cd api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python modelo_provisorio/treinar.py   # grava o pacote em modelo_local/
python -m pytest                      # testes
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

Chamada de exemplo (o corpo em arquivo evita problema de acento no terminal
do Windows):

```bash
curl -X POST localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"satelite": "NOAA-20", "data_hora_gmt": "2026-10-14T18:42:00Z", "lat": -9.51, "lon": -56.20,
       "bioma": "Cerrado", "numero_dias_sem_chuva": 21, "precipitacao": 0.0, "risco_fogo": 0.97}'
```

Também há o corpo pronto em `exemplos/foco.json`, para usar com
`--data-binary @exemplos/foco.json` ou importar no Postman.

## Docker

A imagem (`python:3.12-slim-bookworm`) leva só `requirements.txt` e `app/`,
roda sem root e escuta na porta da variável `PORT`. O modelo não vai na
imagem: a API baixa o pacote de `MODELO_URI` ao subir, então trocar de modelo
não exige reconstruir.

```bash
docker build -t api-foco-intenso api/
docker run --rm -p 8080:8080 -e MODELO_URI=/modelo \
  -v "$PWD/api/modelo_local:/modelo:ro" api-foco-intenso
```

## Deploy no Cloud Run

Pré-requisito: `bash infra/00_setup_all.sh`, que já cria a conta de serviço
da API (só leitura no bucket) e o repositório Docker (`09_artifact_registry.sh`).

```bash
python api/modelo_provisorio/treinar.py   # 1. pacote do modelo provisório
bash api/publicar_modelo.sh               # 2. envia para gs://<BUCKET>/modelos/foco_intenso/provisorio/
bash api/deploy.sh                        # 3. build, deploy e teste na URL pública
bash api/medir_latencia.sh                # 4. mediana e p95 do /predict
```

| Script | O que faz |
|---|---|
| `publicar_modelo.sh [--pasta P] [--versao V]` | Copia um pacote para `modelos/foco_intenso/<V>/` no bucket |
| `deploy.sh [--modelo V] [--min N]` | Cloud Build -> Artifact Registry (tag = commit) -> Cloud Run; chama `/health` e `/predict` no fim |
| `medir_latencia.sh [URL] [N]` | N chamadas a `/predict`; a primeira à parte (cold start), depois mediana e p95 |

Configuração do serviço (`config.env`): 1 CPU, `CLOUD_RUN_MEMORIA`, no
máximo `CLOUD_RUN_MAX_INSTANCIAS` instâncias, acesso público (a URL vai para
o professor), `--cpu-boost` para encurtar o cold start e 0 instâncias mínimas.
No dia da apresentação, `bash api/deploy.sh --min 1`, e depois de volta para 0.

## Ainda falta

- Pacote do modelo real exportado do BigQuery ML e teste de paridade com
  `model/paridade.jsonl` (D5).
