import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from modelo_provisorio.treinar import treinar


@pytest.fixture(scope="session")
def pasta_modelo(tmp_path_factory):
    """Pacote do modelo provisório, treinado uma vez para todos os testes."""
    return treinar(tmp_path_factory.mktemp("modelo"))


@pytest.fixture
def cliente(pasta_modelo, monkeypatch):
    monkeypatch.setattr(config, "MODELO_URI", str(pasta_modelo))
    with TestClient(app) as cliente:  # O "with" roda o carregamento do modelo
        yield cliente


@pytest.fixture
def foco():
    """Exemplo do contrato (docs/contracts.md)."""
    return {
        "satelite": "NOAA-20",
        "data_hora_gmt": "2026-10-14T18:42:00Z",
        "lat": -9.51,
        "lon": -56.20,
        "bioma": "Amazônia",
        "numero_dias_sem_chuva": 21,
        "precipitacao": 0.0,
        "risco_fogo": 0.97,
    }
