"""Rotas da API.

  GET  /health   Confirma que o modelo está carregado (usado para aquecer o serviço)
  POST /predict  Recebe um foco, real ou hipotético, e devolve a probabilidade

O modelo é carregado uma vez, quando o contêiner sobe. Se o pacote não puder
ser lido, a API nem chega a responder, e o erro aparece no log do Cloud Run.

Executar local: uvicorn app.main:app --reload (dentro de api/)
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from . import config
from .features import preparar_variaveis
from .modelo import Modelo
from .schemas import FocoEntrada, Previsao, Saude

# =============================================================================
# Constantes
# =============================================================================
CABECALHO_TEMPO = "X-Tempo-Processamento-Ms"
CASAS_DECIMAIS = 4  # A paridade com o BigQuery é conferida até a 4ª casa
# =============================================================================

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    app.state.modelo = Modelo.carregar(config.MODELO_URI)
    yield


app = FastAPI(
    title="API foco intenso",
    description="Probabilidade de um foco de calor do INPE ser intenso (FRP acima do limiar da sua órbita).",
    lifespan=ciclo_de_vida,
)


@app.middleware("http")
async def medir_tempo(request: Request, call_next):
    inicio = time.perf_counter()
    resposta = await call_next(request)
    resposta.headers[CABECALHO_TEMPO] = f"{(time.perf_counter() - inicio) * 1000:.1f}"
    return resposta


@app.get("/health", response_model=Saude)
def health(request: Request) -> Saude:
    return Saude(status="ok", versao_modelo=request.app.state.modelo.versao)


@app.post("/predict", response_model=Previsao)
def predict(foco: FocoEntrada, request: Request) -> Previsao:
    modelo: Modelo = request.app.state.modelo

    tipo_orbita = modelo.tipo_orbita(foco.satelite)
    if tipo_orbita is None:
        # Mesmo formato dos erros 422 do FastAPI, para o cliente tratar tudo igual
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "satelite_desconhecido",
                    "loc": ["body", "satelite"],
                    "msg": f"Satélite fora da tabela satelites: {foco.satelite}",
                    "input": foco.satelite,
                }
            ],
        )

    probabilidade = modelo.probabilidade(preparar_variaveis(foco, tipo_orbita))
    return Previsao(
        probabilidade_intenso=round(probabilidade, CASAS_DECIMAIS),
        intenso=probabilidade >= modelo.limiar_decisao,
        versao_modelo=modelo.versao,
    )
