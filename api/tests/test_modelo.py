import math
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


def test_codificacao_segue_a_ordem_do_manifest(pasta_modelo):
    vetor = Modelo.carregar(str(pasta_modelo)).codificar(linha())[0]
    # lat, lon, hora, mes | geoestacionario, polar | 6 biomas | dias, precipitacao, risco
    assert list(vetor[:4]) == pytest.approx([-9.5, -56.2, 18, 10])
    assert list(vetor[4:6]) == [0.0, 1.0]
    assert list(vetor[6:12]) == [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]  # Cerrado é o 3º
    assert len(vetor) == 15


def test_nulo_vira_nan(pasta_modelo):
    vetor = Modelo.carregar(str(pasta_modelo)).codificar(linha(risco_fogo=None))[0]
    assert math.isnan(vetor[-1])


def test_probabilidade_entre_0_e_1_mesmo_sem_clima(pasta_modelo):
    modelo = Modelo.carregar(str(pasta_modelo))
    sem_clima = linha(numero_dias_sem_chuva=None, precipitacao=None, risco_fogo=None)
    assert 0 <= modelo.probabilidade(sem_clima) <= 1


def test_carrega_do_cloud_storage(pasta_modelo, monkeypatch):
    """Simula o bucket com uma pasta local, sem rede."""
    baixados = []

    def baixar_falso(uri, nomes, destino):
        for nome in nomes:
            shutil.copyfile(pasta_modelo / nome, destino / nome)
            baixados.append(nome)

    monkeypatch.setattr(modulo_modelo, "_baixar_do_gcs", baixar_falso)
    modelo = Modelo.carregar("gs://bucket-falso/modelos/foco_intenso/v1")
    assert modelo.versao.startswith("foco_intenso")
    assert sorted(baixados) == ["manifest.json", "model.json", "satelites.json"]
