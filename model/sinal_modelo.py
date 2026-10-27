"""C2. Sinal do modelo: XGBoost local contra os dois baselines, com divisão por tempo.

Lê a Gold de treino (focos.gold_treino, A7), que já traz as variáveis, o
rótulo e o conjunto: só focos com FRP, rótulo foco_intenso = frp > limiar de
focos.limiar_frp (C1), treino de out/2025 a ago/2026 e teste em set/2026.

Variáveis, só o que se sabe no instante da detecção (plano, seção "O modelo"):
lat, lon, hora, mes, tipo_orbita, bioma, numero_dias_sem_chuva, precipitacao
e risco_fogo. O XGBoost recebe a matriz de model/pacote.py, a mesma ordem de
colunas e a mesma codificação que a API usa.

Compara, no mês de teste:
  - XGBoost com as variáveis do plano;
  - XGBoost sem mes (set/2026 não aparece no treino, então o mês do teste é
    sempre um valor que o modelo nunca viu);
  - baseline A: sempre a classe majoritária do treino;
  - baseline B: regressão logística só com tipo_orbita e hora.

No fim, grava as métricas e a decisão em model/README.md, na seção da C2
(rodar de novo substitui a seção, não duplica).

Uso (a partir da raiz do repositório):
    pip install -r model/requirements.txt
    set -a; source config.env; set +a
    python3 model/sinal_modelo.py
    python3 model/sinal_modelo.py --sem-readme   # só imprime as métricas
"""

import argparse
import datetime as dt
import os
import re

import numpy as np
import pandas as pd
import xgboost as xgb
from google.cloud import bigquery
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

import pacote

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")

TABELA_GOLD = f"{PROJECT_ID}.{DATASET}.gold_treino"
LIMITE_GB_CONSULTA = 2

ROTULO = "foco_intenso"
VARIAVEIS_BASELINE = ["tipo_orbita", "hora"]   # Baseline B, as duas tratadas como categorias

PARAMETROS_XGB = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
    "eval_metric": "auc",
    "n_jobs": -1,
    "random_state": 42,
}
ALVO_AUC = 0.70          # Critério do plano para o XGBoost
MARGEM_SOBRE_BASELINE = 0.05   # "Ganhar claramente" da regressão logística

CAMINHO_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
MARCA_INICIO = "<!-- C2: início (gerado por model/sinal_modelo.py) -->"
MARCA_FIM = "<!-- C2: fim -->"
# =============================================================================


CONSULTA_GOLD = f"SELECT * FROM `{TABELA_GOLD}`"


def consultar(cliente, sql) -> pd.DataFrame:
    """Roda uma consulta com dry run antes e limite de bytes."""
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > limite:
        raise RuntimeError(f"Consulta leria mais de {LIMITE_GB_CONSULTA} GB; confira o filtro de partição.")
    print(f"Consulta vai ler {estimativa / 1024**2:,.1f} MB")
    job = cliente.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=limite))
    return job.to_dataframe()


def matriz_modelo(focos) -> pd.DataFrame:
    """As variáveis do plano na ordem e na codificação da API (model/pacote.py)."""
    return pd.DataFrame(pacote.montar_matriz(focos), columns=pacote.nomes_colunas(), index=focos.index)


def matriz_baseline(focos) -> pd.DataFrame:
    """Baseline B: tipo_orbita e hora, as duas em one-hot."""
    return pd.concat([pd.get_dummies(focos[c].astype("string"), prefix=c, dtype="float64")
                      for c in VARIAVEIS_BASELINE], axis=1)


def metricas(y, score) -> dict[str, float]:
    return {"roc_auc": roc_auc_score(y, score), "pr_auc": average_precision_score(y, score)}


def treinar_xgboost(x_treino, y_treino, x_teste, y_teste) -> tuple[dict[str, float], pd.Series]:
    # Mesmo efeito do auto_class_weights do BigQuery ML: a classe rara pesa mais
    peso_positivo = (y_treino == 0).sum() / max((y_treino == 1).sum(), 1)
    modelo = xgb.XGBClassifier(**PARAMETROS_XGB, scale_pos_weight=peso_positivo)
    modelo.fit(x_treino, y_treino)
    score = modelo.predict_proba(x_teste)[:, 1]
    importancia = pd.Series(modelo.get_booster().get_score(importance_type="gain")).sort_values(ascending=False)
    return metricas(y_teste, score), importancia


def avaliar(focos) -> dict:
    treino, teste = focos[focos["conjunto"] == "treino"], focos[focos["conjunto"] == "teste"]
    y_treino, y_teste = treino[ROTULO].astype(int), teste[ROTULO].astype(int)
    resultado = {
        "focos_treino": len(treino),
        "focos_teste": len(teste),
        "pct_intensos_treino": 100 * y_treino.mean(),
        "pct_intensos_teste": 100 * y_teste.mean(),
    }

    # Baseline A: sempre a classe majoritária do treino (score constante, ROC AUC = 0,5)
    majoritaria = int(y_treino.mean() >= 0.5)
    score_constante = np.full(len(teste), float(majoritaria))
    resultado["majoritaria"] = metricas(y_teste, score_constante)
    resultado["majoritaria"]["acuracia"] = float((y_teste == majoritaria).mean())

    # Baseline B: regressão logística com tipo_orbita e hora, ambas em one-hot
    x = matriz_baseline(focos)
    logistica = LogisticRegression(max_iter=1000, class_weight="balanced")
    logistica.fit(x.loc[treino.index], y_treino)
    resultado["logistica"] = metricas(y_teste, logistica.predict_proba(x.loc[teste.index])[:, 1])

    # XGBoost com as variáveis do plano, e a mesma coisa sem mes
    x = matriz_modelo(focos)
    resultado["xgboost"], resultado["importancia"] = treinar_xgboost(
        x.loc[treino.index], y_treino, x.loc[teste.index], y_teste)
    x = x.drop(columns="mes")
    resultado["xgboost_sem_mes"], _ = treinar_xgboost(x.loc[treino.index], y_treino, x.loc[teste.index], y_teste)
    return resultado


def decidir(r) -> str:
    auc, auc_log = r["xgboost"]["roc_auc"], r["logistica"]["roc_auc"]
    ganho = auc - auc_log
    if auc >= ALVO_AUC and ganho >= MARGEM_SOBRE_BASELINE:
        decisao = (f"**Seguir com as variáveis do plano.** O XGBoost passa do alvo de {ALVO_AUC:.2f} de "
                   f"ROC AUC e ganha da regressão logística por {ganho:.3f}.")
    elif auc >= ALVO_AUC:
        decisao = (f"**Ajustar.** O XGBoost passa do alvo de {ALVO_AUC:.2f}, mas ganha da regressão logística "
                   f"só por {ganho:.3f} (menos que {MARGEM_SOBRE_BASELINE:.2f}): quase todo o sinal vem da órbita "
                   f"e da hora. Rever o limiar e as variáveis, como o plano prevê.")
    else:
        decisao = (f"**Ajustar.** O XGBoost fica abaixo do alvo de {ALVO_AUC:.2f}. Rever o limiar e as "
                   f"variáveis; se não bastar, seguir e dizer isso nos slides, porque a acurácia não é avaliada.")
    diferenca_mes = r["xgboost"]["roc_auc"] - r["xgboost_sem_mes"]["roc_auc"]
    nota_mes = (f"Sem `mes`, o ROC AUC muda em {-diferenca_mes:+.3f}. Set/2026 não aparece no treino, "
                f"então no teste o mês é sempre um valor que o modelo nunca viu.")
    return f"{decisao}\n\n{nota_mes}"


def milhar(valor) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def texto_readme(r) -> str:
    def linha(nome, m):
        return f"| {nome} | {m['roc_auc']:.3f} | {m['pr_auc']:.3f} |"

    importancia = ", ".join(f"`{nome}` ({valor:,.0f})" for nome, valor in r["importancia"].head(8).items())
    return "\n".join([
        MARCA_INICIO,
        "## C2. Sinal do modelo",
        "",
        f"Gerado por `model/sinal_modelo.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC. "
        "XGBoost local sobre a Gold de treino (`focos.gold_treino`): treino de out/2025 a ago/2026 e "
        "teste em set/2026, só focos com FRP, rótulo pelo limiar de `focos.limiar_frp`, matriz na ordem "
        f"e na codificação da API (`model/pacote.py`, xgboost {xgb.__version__}).",
        "",
        f"- Treino: {milhar(r['focos_treino'])} focos, {r['pct_intensos_treino']:.1f}% intensos.",
        f"- Teste: {milhar(r['focos_teste'])} focos, {r['pct_intensos_teste']:.1f}% intensos.",
        "",
        "| Modelo (mês de teste) | ROC AUC | PR AUC |",
        "|---|---|---|",
        linha("XGBoost, variáveis do plano", r["xgboost"]),
        linha("XGBoost sem `mes`", r["xgboost_sem_mes"]),
        linha("Baseline B: regressão logística (`tipo_orbita`, `hora`)", r["logistica"]),
        linha("Baseline A: sempre a classe majoritária", r["majoritaria"]),
        "",
        f"O baseline A tem acurácia de {100 * r['majoritaria']['acuracia']:.1f}% sem aprender nada, e por isso "
        "a comparação usa ROC AUC. A PR AUC mostra o ganho na classe rara (a de um classificador "
        "sem sinal é a própria parcela de intensos).",
        "",
        f"Variáveis mais importantes do XGBoost (ganho): {importancia}.",
        "",
        "### Decisão",
        "",
        decidir(r),
        MARCA_FIM,
    ])


def atualizar_readme(texto) -> None:
    with open(CAMINHO_README, encoding="utf-8") as arquivo:
        atual = arquivo.read()
    padrao = re.compile(re.escape(MARCA_INICIO) + r".*?" + re.escape(MARCA_FIM), re.DOTALL)
    if padrao.search(atual):
        novo = padrao.sub(lambda _m: texto, atual)
    else:
        novo = atual.rstrip("\n") + "\n\n" + texto
    with open(CAMINHO_README, "w", encoding="utf-8") as arquivo:
        arquivo.write(novo + "\n" if not novo.endswith("\n") else novo)
    print(f"\nMétricas e decisão gravadas em {CAMINHO_README}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-readme", action="store_true", help="Só imprime as métricas, sem mexer no README")
    args = parser.parse_args()

    cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)
    focos = consultar(cliente, CONSULTA_GOLD)
    print(f"{len(focos):,} focos lidos de {TABELA_GOLD}; treinando (pode levar alguns minutos)...")
    resultado = avaliar(focos)

    texto = texto_readme(resultado)
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
