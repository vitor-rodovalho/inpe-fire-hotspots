"""Treina o modelo provisório e grava o pacote que a API carrega.

Serve para colocar a API no ar antes de o modelo real existir: tem as mesmas
entradas e o mesmo formato de pacote, mas é treinado com dados sintéticos e
não deve ser usado para nada além de testar a API, o Docker e o deploy.

A relação imitada nos dados é a esperada: mais risco de fogo e mais dias sem
chuva aumentam a chance de um foco ser intenso, e chuva diminui.

Uso (dentro de api/):
  python modelo_provisorio/treinar.py                  # grava em modelo_local/
  python modelo_provisorio/treinar.py --saida /tmp/m   # outra pasta
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import xgboost as xgb

# =============================================================================
# Constantes
# =============================================================================
RAIZ_REPO = Path(__file__).resolve().parents[2]
SATELITES_PADRAO = RAIZ_REPO / "pipeline" / "references_example.json"
SAIDA_PADRAO = Path(__file__).resolve().parents[1] / "modelo_local"

VERSAO = "foco_intenso_provisorio_v0"
ARQUIVO_MODELO = "model.json"
LIMIAR_DECISAO = 0.5
SEMENTE = 42
QTD_LINHAS = 3000
QTD_ARVORES = 40

BIOMAS = ["Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"]
ORBITAS = ["geoestacionario", "polar"]

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
# =============================================================================


def dados_sinteticos(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    n = QTD_LINHAS
    lat = rng.uniform(-33, 5, n)
    lon = rng.uniform(-73, -35, n)
    hora = rng.integers(0, 24, n)
    mes = rng.integers(1, 13, n)
    orbita = rng.integers(0, len(ORBITAS), n)
    bioma = rng.integers(0, len(BIOMAS), n)
    dias = rng.integers(0, 60, n).astype(float)
    precipitacao = rng.exponential(2.0, n)
    risco = rng.uniform(0, 1, n)

    logit = -3.0 + 3.0 * risco + 0.04 * dias - 0.3 * precipitacao + 0.5 * (orbita == 0)
    rotulo = rng.uniform(0, 1, n) < 1 / (1 + np.exp(-logit))

    colunas = [lat, lon, hora, mes]
    colunas += [(orbita == i).astype(float) for i in range(len(ORBITAS))]
    colunas += [(bioma == i).astype(float) for i in range(len(BIOMAS))]
    colunas += [dias, precipitacao, risco]
    return np.column_stack(colunas).astype(np.float32), rotulo.astype(int)


def treinar(saida: Path, satelites: Path = SATELITES_PADRAO) -> Path:
    x, y = dados_sinteticos(np.random.default_rng(SEMENTE))
    booster = xgb.train(
        {"objective": "binary:logistic", "max_depth": 3, "eta": 0.2, "seed": SEMENTE},
        xgb.DMatrix(x, label=y),
        num_boost_round=QTD_ARVORES,
    )

    saida.mkdir(parents=True, exist_ok=True)
    booster.save_model(saida / ARQUIVO_MODELO)
    manifesto = {
        "versao_modelo": VERSAO,
        "arquivo_modelo": ARQUIVO_MODELO,
        "limiar_decisao": LIMIAR_DECISAO,
        "variaveis": VARIAVEIS,
    }
    (saida / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(satelites, saida / "satelites.json")
    return saida


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Pasta do pacote")
    parser.add_argument("--satelites", type=Path, default=SATELITES_PADRAO, help="JSON satélite -> órbita")
    args = parser.parse_args()
    print(f"Pacote do modelo provisório gravado em {treinar(args.saida, args.satelites)}")


if __name__ == "__main__":
    main()
