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

## Ainda falta

- Dockerfile e `deploy.sh` para o Cloud Run (D4).
- Pacote do modelo real exportado do BigQuery ML e teste de paridade com
  `model/paridade.jsonl` (D5).
