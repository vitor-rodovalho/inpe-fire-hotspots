import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

TOKEN = "token-de-teste-123"


@pytest.fixture
def cliente_protegido(pasta_modelo, monkeypatch):
    monkeypatch.setattr(config, "MODELO_URI", str(pasta_modelo))
    monkeypatch.setattr(config, "API_TOKEN", TOKEN)
    with TestClient(app) as cliente:
        yield cliente


def test_token_certo_passa(cliente_protegido, foco):
    resposta = cliente_protegido.post("/predict", json=foco, headers={"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 200


@pytest.mark.parametrize(
    "cabecalhos",
    [{}, {"Authorization": "Bearer errado"}, {"Authorization": TOKEN}, {"Authorization": f"Basic {TOKEN}"}],
)
def test_sem_token_ou_token_errado_da_401(cliente_protegido, foco, cabecalhos):
    resposta = cliente_protegido.post("/predict", json=foco, headers=cabecalhos)
    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


def test_token_e_conferido_antes_do_corpo(cliente_protegido):
    """Sem token, um corpo inválido dá 401 e não 422: nada do contrato vaza."""
    assert cliente_protegido.post("/predict", json={"lat": 999}).status_code == 401


def test_health_e_docs_continuam_abertos(cliente_protegido):
    assert cliente_protegido.get("/health").status_code == 200
    assert cliente_protegido.get("/docs").status_code == 200


def test_swagger_mostra_o_botao_authorize(cliente_protegido):
    esquemas = cliente_protegido.get("/openapi.json").json()["components"]["securitySchemes"]
    assert esquemas["HTTPBearer"]["scheme"] == "bearer"
