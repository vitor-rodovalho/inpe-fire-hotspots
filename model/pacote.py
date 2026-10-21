"""Pacote do modelo no formato que a API lê (api/README.md, branch frente-d/api).

Uma pasta com três arquivos:
  manifest.json   versao_modelo, arquivo_modelo, limiar_decisao e a lista
                  ordenada de variáveis, com as categorias das categóricas
  satelites.json  {"satelites": {satelite: tipo_orbita}}
  model.json      Booster do XGBoost em JSON

A API monta o vetor de entrada pela ordem de VARIAVEIS: numéricas como número
(nulo vira NaN) e categóricas em one-hot, uma coluna por categoria, na ordem da
lista (valor nulo ou fora da lista: todas as colunas em 0). montar_matriz faz
exatamente isso, e é ela que o treino usa, para que o modelo veja no treino as
mesmas colunas, na mesma ordem, que recebe na API.
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

# =============================================================================
# Constantes (as mesmas de api/modelo_provisorio/treinar.py e api/app/schemas.py)
# =============================================================================
ARQUIVO_MODELO = "model.json"
ARQUIVO_MANIFESTO = "manifest.json"
ARQUIVO_SATELITES = "satelites.json"
LIMIAR_DECISAO = 0.5
VERSAO_XGBOOST_API = "2.1.3"   # xgboost-cpu fixado em api/requirements.txt

ORBITAS = ["geoestacionario", "polar"]
BIOMAS = ["Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"]

# Ordem das colunas do vetor; as categóricas viram uma coluna por categoria
VARIAVEIS = [
    {"nome": "lat", "tipo": "numerica"},
    {"nome": "lon", "tipo": "numerica"},
    {"nome": "hora", "tipo": "numerica"},
    {"nome": "mes", "tipo": "numerica"},
    {"nome": "tipo_orbita", "tipo": "categorica", "categorias": ORBITAS},
    {"nome": "bioma", "tipo": "categorica", "categorias": BIOMAS},
    {"nome": "numero_dias_sem_chuva", "tipo": "numerica"},
    {"nome": "precipitacao", "tipo": "numerica"},
    {"nome": "risco_fogo", "tipo": "numerica"},
]

RAIZ_REPO = Path(__file__).resolve().parents[1]
SATELITES_PADRAO = RAIZ_REPO / "pipeline" / "references_example.json"   # Os 12 de focos.satelites
# =============================================================================


def nomes_colunas(variaveis=VARIAVEIS) -> list[str]:
    """Nome de cada coluna do vetor, na ordem, por exemplo bioma=Cerrado."""
    nomes = []
    for variavel in variaveis:
        if variavel["tipo"] == "categorica":
            nomes += [f"{variavel['nome']}={categoria}" for categoria in variavel["categorias"]]
        else:
            nomes.append(variavel["nome"])
    return nomes


def montar_matriz(focos, variaveis=VARIAVEIS) -> np.ndarray:
    """DataFrame com as colunas da Gold para a matriz na ordem do manifest, igual à API."""
    colunas = []
    for variavel in variaveis:
        valores = focos[variavel["nome"]]
        if variavel["tipo"] == "categorica":
            colunas += [(valores == categoria).fillna(False).to_numpy(dtype="float32")
                        for categoria in variavel["categorias"]]
        else:
            colunas.append(pd.to_numeric(valores, errors="coerce").to_numpy(dtype="float32"))
    return np.column_stack(colunas).astype(np.float32)


def ler_satelites(caminho=SATELITES_PADRAO) -> dict[str, str]:
    with open(caminho, encoding="utf-8") as arquivo:
        return dict(json.load(arquivo)["satelites"])


def salvar_pacote(booster, pasta, versao, satelites, variaveis=VARIAVEIS) -> Path:
    """Grava model.json, manifest.json e satelites.json numa pasta local."""
    pasta = Path(pasta)
    os.makedirs(pasta, exist_ok=True)
    booster.save_model(pasta / ARQUIVO_MODELO)
    manifesto = {
        "versao_modelo": versao,
        "arquivo_modelo": ARQUIVO_MODELO,
        "limiar_decisao": LIMIAR_DECISAO,
        "variaveis": variaveis,
        "xgboost": xgb.__version__,
    }
    (pasta / ARQUIVO_MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / ARQUIVO_SATELITES).write_text(
        json.dumps({"satelites": satelites}, ensure_ascii=False, indent=2), encoding="utf-8")
    return pasta
