"""Treina o modelo provisório e grava um pacote no formato do export do BigQuery ML.

Serve para testar a API, o Docker e o deploy sem o modelo real e sem nuvem. O
pacote imita o que o EXPORT MODEL grava para um boosted tree (model/README.md,
seção C3): Booster multi:softprob com as classes ["true", "false"], uma coluna
por variável, categóricas como índice no vocabulário e as médias do treino em
assets/model_metadata.json. Assim, os testes passam pelo mesmo código que
carrega o modelo real.

Os dados são sintéticos, com a relação esperada: mais risco de fogo e mais dias
sem chuva aumentam a chance de um foco ser intenso, e chuva diminui. Não use
este modelo para nada além de testar a API.

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

CLASSES = ["true", "false"]  # Mesma ordem do export: a classe 0 é "intenso"
NULO = "_null_filler"  # O BigQuery ML reserva o índice 0 do vocabulário para o nulo
ORBITAS = [NULO, "geoestacionario", "polar"]
BIOMAS = [NULO, "Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"]

# Ordem das colunas, como em feature_names do export
VARIAVEIS = ["lat", "lon", "hora", "mes", "tipo_orbita", "bioma",
             "numero_dias_sem_chuva", "precipitacao", "risco_fogo"]  # fmt: skip
VOCABULARIOS = {4: ORBITAS, 5: BIOMAS}  # Índice da variável: vocabulário
# =============================================================================


def dados_sinteticos(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    n = QTD_LINHAS
    orbita = rng.integers(1, len(ORBITAS), n)  # Índices, sem o nulo
    bioma = rng.integers(1, len(BIOMAS), n)
    dias = rng.integers(0, 60, n).astype(float)
    precipitacao = rng.exponential(2.0, n)
    risco = rng.uniform(0, 1, n)
    x = np.column_stack([
        rng.uniform(-33, 5, n), rng.uniform(-73, -35, n),   # lat, lon
        rng.integers(0, 24, n), rng.integers(1, 13, n),     # hora, mes
        orbita, bioma, dias, precipitacao, risco,
    ]).astype(float)  # fmt: skip

    logit = -3.0 + 3.0 * risco + 0.04 * dias - 0.3 * precipitacao + 0.5 * (orbita == 1)
    intenso = rng.uniform(0, 1, n) < 1 / (1 + np.exp(-logit))
    return x, np.where(intenso, CLASSES.index("true"), CLASSES.index("false"))


def treinar(saida: Path, satelites: Path = SATELITES_PADRAO) -> Path:
    x, y = dados_sinteticos(np.random.default_rng(SEMENTE))
    booster = xgb.train(
        {"objective": "multi:softprob", "num_class": len(CLASSES), "max_depth": 3, "eta": 0.2, "seed": SEMENTE},
        xgb.DMatrix(x, label=y),
        num_boost_round=QTD_ARVORES,
    )

    assets = saida / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    booster.save_model(saida / ARQUIVO_MODELO)
    metadados = {
        "feature_names": VARIAVEIS,
        "features": {nome: {"mean": float(x[:, i].mean())}
                     for i, nome in enumerate(VARIAVEIS) if i not in VOCABULARIOS},  # fmt: skip
        "class_names": CLASSES,
    }
    (assets / "model_metadata.json").write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    for i, vocabulario in VOCABULARIOS.items():
        (assets / f"{i}_categorical_label.txt").write_text("\n".join(vocabulario) + "\n", encoding="utf-8")

    manifesto = {"versao_modelo": VERSAO, "arquivo_modelo": ARQUIVO_MODELO, "limiar_decisao": LIMIAR_DECISAO}
    (saida / "manifest.json").write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
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
