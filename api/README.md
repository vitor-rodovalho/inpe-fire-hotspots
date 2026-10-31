# API foco intenso (Frente D)

API REST que recebe um foco de calor, real ou hipotético, e devolve a
probabilidade de ele ser intenso. O modelo é o boosted tree do BigQuery ML
(`focos.modelo_foco_intenso`, registrado no Vertex AI), exportado e servido em
FastAPI no Cloud Run como `api-foco-intenso`.

```
POST /predict  {"satelite": "NOAA-20", "data_hora_gmt": "2026-10-14T18:42:00Z", ...}
            -> {"probabilidade_intenso": 0.7132, "intenso": true, "versao_modelo": "foco_intenso_v1"}
GET  /health   {"status": "ok", "versao_modelo": "foco_intenso_v1"}
GET  /docs     Documentação interativa (gerada pelo FastAPI)
```

Toda resposta traz o cabeçalho `X-Tempo-Processamento-Ms`, o tempo gasto
dentro da API, sem a rede. Paridade e latência medidas no Cloud Run:
[docs/api_evidence.md](../docs/api_evidence.md).

## Subir tudo com um comando

No Cloud Shell, no projeto `inpe-fire-hotspots`:

```bash
git clone https://github.com/vitor-rodovalho/inpe-fire-hotspots.git && cd inpe-fire-hotspots && bash api/subir_api.sh
```

| Etapa | O que faz | Custo |
|---|---|---|
| 1 a 4 | Confere acesso e conta de serviço, liga as APIs, cria o repositório Docker | US$ 0 |
| 5 | Monta o pacote v1 (`montar_pacote_v1.py`): `EXPORT MODEL`, 50 focos de paridade com o `ML.PREDICT` e a conferência local. Pula se já estiver pronto | Centavos (lê alguns MB) |
| 6 | Build no Cloud Build, imagem no Artifact Registry, deploy no Cloud Run | US$ 0 (cota gratuita) |
| 7 | Testa a URL pública (`testar_api.py`) e grava `docs/api_evidence.md` | US$ 0 |

Para no primeiro erro dizendo o que fazer, e pode ser rodado de novo. Se
faltar uma permissão (acesso ao projeto, Cloud Build ou acesso público), a
mensagem traz o comando que o dono do projeto precisa rodar.

## Estrutura

```
app/
  main.py      Rotas e carregamento do modelo quando o contêiner sobe
  schemas.py   Contrato: campos, tipos e faixas válidas (fora delas, 422)
  features.py  Entrada -> variáveis do modelo, calculadas como na Gold
  modelo.py    Lê o pacote (pasta local ou gs://) e monta o vetor como o ML.PREDICT
  config.py    Variáveis de ambiente
modelo_provisorio/
  treinar.py   Modelo de teste no formato do export, com dados sintéticos
tests/         pytest, sem nuvem
montar_pacote_v1.py   C5: export do modelo real, paridade e publicação do pacote
testar_api.py         Testa a API no ar: paridade, erros 422 e latência
```

## Contrato

| Campo | Tipo | Regra |
|---|---|---|
| `satelite` | texto | Precisa estar na tabela `satelites` (senão 422) |
| `data_hora_gmt` | data e hora | ISO 8601 ou o formato do INPE (`2026-10-14 18:42:00`); sem fuso, é GMT |
| `lat`, `lon` | número | Dentro do retângulo do Brasil (o mesmo do pipeline) |
| `bioma` | texto, opcional | Um dos seis biomas do INPE; ausente ou vazio vira nulo |
| `numero_dias_sem_chuva` | número, opcional | `>= 0`; vazio ou `-999` vira nulo |
| `precipitacao` | número, opcional | `>= 0`; vazio ou `-999` vira nulo |
| `risco_fogo` | número, opcional | De 0 a 1; vazio ou `-999` vira nulo |

O FRP não entra: é o que o modelo estima. Campos a mais são ignorados, então
uma linha da Silver pode ser enviada como está. `intenso` é
`probabilidade_intenso >= 0,5`, o mesmo limiar do `ML.PREDICT`. Como o modelo
foi treinado com `auto_class_weights`, a probabilidade não é calibrada e esse
limiar marca mais intensos do que existem (ver `docs/model_metrics.md`).

## Como o modelo responde igual ao BigQuery

O boosted tree exportado não recebe as variáveis como um XGBoost comum. O
`modelo.py` monta o vetor como o `ML.PREDICT` monta (descoberto na C3,
`model/README.md`):

| Variável | Vira |
|---|---|
| `lat`, `lon`, `hora`, `mes`, clima | O valor; **nulo vira a média do treino** (de `assets/model_metadata.json`) |
| `tipo_orbita`, `bioma` | **O índice no vocabulário** (`assets/<i>_categorical_label.txt`), não one-hot; nulo ou desconhecido vira 0 (`_null_filler`) |

A saída tem uma coluna por classe, na ordem `["true", "false"]`; a
probabilidade de intenso é a da classe `"true"`. `hora` e `mes` saem de
`data_hora_gmt` em GMT, como na Gold, e `tipo_orbita` vem de `satelites.json`.

**A prova:** `montar_pacote_v1.py` só publica o pacote se os 50 focos de
`model/paridade.jsonl` (40 completos, 5 com clima nulo e 5 sem bioma) derem,
passando pelo código da API, a mesma probabilidade do `ML.PREDICT` com
diferença de até 1e-6. Depois, `testar_api.py` repete a conferência contra a
URL pública, até a 4ª casa.

## Pacote do modelo

Fica em `gs://<BUCKET>/modelos/foco_intenso/v1/`: os arquivos do `EXPORT MODEL`
mais três gravados por `montar_pacote_v1.py`. A variável de ambiente
`MODELO_URI` diz onde ele está.

| Arquivo | De onde vem | Conteúdo |
|---|---|---|
| `manifest.json` | `montar_pacote_v1.py` | Versão, arquivo do Booster e limiar de decisão |
| `satelites.json` | `montar_pacote_v1.py`, de `focos.satelites` | Satélite para tipo de órbita |
| `model.json` | `montar_pacote_v1.py` | O Booster do export salvo no formato atual do XGBoost |
| `model.bst` | `EXPORT MODEL` | O Booster no formato do XGBoost 0.82 (reserva, caso o JSON não passe na paridade) |
| `assets/` | `EXPORT MODEL` | Ordem das variáveis, médias, classes e vocabulários |

A API baixa só esses arquivos; o servidor de exemplo que vem no export não é
usado.

## Rodar na máquina

```bash
cd api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python modelo_provisorio/treinar.py   # pacote de teste, no formato do export, em modelo_local/
python -m pytest                      # testes, sem nuvem
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

Chamada de exemplo com o corpo pronto em `exemplos/foco.json` (o arquivo
evita problema de acento no terminal do Windows; também serve para o Postman):

```bash
curl -X POST localhost:8000/predict -H "Content-Type: application/json" --data-binary @exemplos/foco.json
```

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

## Scripts

| Script | O que faz |
|---|---|
| `subir_api.sh [--modelo V] [--min N]` | Tudo em sequência, com as checagens de acesso (padrão: `MODELO_VERSAO` de `config.env`, `v1`) |
| `montar_pacote_v1.py [--so-validar]` | C5: export, `satelites.json`, `manifest.json`, `model/paridade.jsonl`, conferência e publicação |
| `deploy.sh [--modelo V] [--min N]` | Cloud Build -> Artifact Registry (tag = commit) -> Cloud Run; chama `/health` e `/predict` no fim |
| `testar_api.py URL [--gravar]` | Paridade, erros 422 e latência na URL; com `--gravar`, escreve `docs/api_evidence.md` |
| `instancias_minimas.sh 0\|1` | Liga ou desliga a instância sempre ativa, sem novo build (dia da apresentação) |
| `publicar_modelo.sh [--pasta P] [--versao V]` | Copia um pacote local para `modelos/foco_intenso/<V>/` (usado pelo modelo provisório) |
| `medir_latencia.sh [URL] [N]` | N chamadas a `/predict`: a primeira à parte (cold start), depois mediana e p95 |

Configuração do serviço (`config.env`): 1 CPU, `CLOUD_RUN_MEMORIA`, no
máximo `CLOUD_RUN_MAX_INSTANCIAS` instâncias, acesso público (a URL vai para
o professor), `--cpu-boost` para encurtar o cold start e 0 instâncias mínimas.
A demo da apresentação fica em `scripts/demo.py`, e o roteiro do dia em
[docs/checklist_apresentacao.md](../docs/checklist_apresentacao.md).
