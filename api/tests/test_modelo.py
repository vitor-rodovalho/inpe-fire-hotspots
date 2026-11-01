import json
import shutil

import pytest

from app import modelo as modulo_modelo
from app.modelo import Modelo


def linha(**alteracoes):
    base = {
        "lat": -9.5, "lon": -56.2, "hora": 18, "mes": 10, "tipo_orbita": "polar", "bioma": "Cerrado",
        "numero_dias_sem_chuva": 21.0, "precipitacao": 0.0, "risco_fogo": 0.9,
    }  # fmt: skip
    return base | alteracoes


@pytest.fixture
def modelo(pasta_modelo):
    return Modelo.carregar(str(pasta_modelo))


def test_uma_coluna_por_variavel_na_ordem_do_export(modelo):
    vetor = modelo.codificar(linha())[0]
    # lat, lon, hora, mes, tipo_orbita, bioma, dias, precipitacao, risco
    assert list(vetor) == pytest.approx([-9.5, -56.2, 18, 10, 2, 3, 21.0, 0.0, 0.9])


def test_categorica_vira_indice_no_vocabulario(modelo):
    assert modelo.codificar(linha(tipo_orbita="geoestacionario", bioma="Amazônia"))[0][4:6].tolist() == [1, 1]


def test_categorica_nula_ou_desconhecida_vira_null_filler(modelo):
    assert modelo.codificar(linha(bioma=None))[0][5] == 0
    assert modelo.codificar(linha(bioma="Savana"))[0][5] == 0


def test_numerica_nula_vira_media_do_treino(modelo, pasta_modelo):
    medias = json.loads((pasta_modelo / "assets" / "model_metadata.json").read_text(encoding="utf-8"))["features"]
    vetor = modelo.codificar(linha(numero_dias_sem_chuva=None, precipitacao=None, risco_fogo=None))[0]
    assert list(vetor[6:]) == pytest.approx(
        [medias["numero_dias_sem_chuva"]["mean"], medias["precipitacao"]["mean"], medias["risco_fogo"]["mean"]]
    )


def test_probabilidade_e_a_coluna_true(modelo):
    """O Booster devolve [P(true), P(false)]; a API usa a primeira."""
    saida = modelo.booster.inplace_predict(modelo.codificar(linha()))[0]
    assert saida.sum() == pytest.approx(1.0, abs=1e-6)
    assert modelo.probabilidade(linha()) == pytest.approx(float(saida[0]))


def test_carrega_do_cloud_storage(pasta_modelo, monkeypatch):
    """Simula o bucket com uma pasta local, sem rede."""
    def baixar_falso(uri, destino):
        shutil.copytree(pasta_modelo, destino, dirs_exist_ok=True)

    monkeypatch.setattr(modulo_modelo, "_baixar_do_gcs", baixar_falso)
    modelo = Modelo.carregar("gs://bucket-falso/modelos/foco_intenso/v1")
    assert modelo.versao == "foco_intenso_provisorio_v0"
    assert 0 <= modelo.probabilidade(linha()) <= 1
