"""Testa a validação de api/montar_pacote_v1.py sem GCP, com o modelo provisório.

O modelo real só existe no GCP; aqui, o "ML.PREDICT" é o próprio modelo
provisório, e o model.bst é uma cópia do model.json. O que se testa é o
caminho: ler a paridade, passar cada foco pela API e escolher o Booster.
"""

import json
import shutil

import pytest

import montar_pacote_v1 as pacote
from app.modelo import Modelo


@pytest.fixture
def pasta(pasta_modelo, tmp_path):
    destino = tmp_path / "pacote"
    shutil.copytree(pasta_modelo, destino)
    shutil.copyfile(destino / "model.json", destino / "model.bst")
    return destino


def gravar_paridade(pasta, caminho, foco, desvio=0.0):
    modelo = Modelo.carregar(str(pasta))
    focos = [foco, foco | {"bioma": None}, foco | {"risco_fogo": None, "precipitacao": None}]
    with caminho.open("w", encoding="utf-8") as arquivo:
        for i, f in enumerate(focos):
            prob = pacote.prever_local(modelo, f) + desvio
            registro = {"grupo": "teste", "id": str(i), "frp": None, "foco": f,
                        "prob_bigquery": prob, "intenso_bigquery": prob >= 0.5}  # fmt: skip
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def test_paridade_passa_e_escolhe_model_json(pasta, tmp_path, foco):
    paridade = tmp_path / "paridade.jsonl"
    gravar_paridade(pasta, paridade, foco)
    assert pacote.validar(pasta, paridade) == "model.json"
    assert json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))["arquivo_modelo"] == "model.json"


def test_paridade_falha_quando_a_probabilidade_diverge(pasta, tmp_path, foco):
    paridade = tmp_path / "paridade.jsonl"
    gravar_paridade(pasta, paridade, foco, desvio=0.01)
    assert pacote.validar(pasta, paridade) is None
