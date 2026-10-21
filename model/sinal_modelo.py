"""C2. Sinal do modelo: XGBoost local contra os dois baselines, com divisão por tempo.

Lê da Bronze os focos de out/2025 a set/2026 e aplica as regras da Silver e do
streaming: apara espaços, converte tipos, trata vazio e -999 como nulo em todas
as colunas numéricas e descarta o que o streaming rejeitaria (coordenada fora
do Brasil, risco de fogo fora de 0 a 1). Focos sem FRP ficam de fora, porque
sem FRP não há rótulo.

O rótulo foco_intenso é frp > limiar, com o limiar de focos.limiar_frp (C1) e
o tipo de órbita de focos.satelites: as mesmas tabelas e a mesma comparação do
Dataflow e da Gold de treino.

Variáveis, só o que se sabe no instante da detecção (plano, seção "O modelo"):
lat, lon, hora, mes, tipo_orbita, bioma, numero_dias_sem_chuva, precipitacao
e risco_fogo. Treino de out/2025 a ago/2026 e teste em set/2026.

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

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")

TABELA_BRONZE = f"{PROJECT_ID}.{DATASET}.bronze_focos_mensal"
TABELA_SATELITES = f"{PROJECT_ID}.{DATASET}.satelites"
TABELA_LIMIAR = f"{PROJECT_ID}.{DATASET}.limiar_frp"

MES_INICIO_TREINO = "2025-10-01"   # Partição mes_referencia da Bronze
MES_TESTE = "2026-09-01"           # Mês de teste; o treino vai até o mês anterior
VALOR_AUSENTE = -999
LAT_MIN, LAT_MAX = -34.0, 5.5      # Os mesmos de pipeline/focos_stream/cleaning.py
LON_MIN, LON_MAX = -74.5, -28.5
LIMITE_GB_CONSULTA = 2

VARIAVEIS_NUMERICAS = ["lat", "lon", "hora", "mes", "numero_dias_sem_chuva", "precipitacao", "risco_fogo"]
VARIAVEIS_CATEGORICAS = ["tipo_orbita", "bioma"]
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


def numero(coluna) -> str:
    """Texto para FLOAT64, com vazio e -999 virando NULL (a regra da Silver e do streaming)."""
    texto = f"TRIM(IFNULL({coluna}, ''))"
    return f"IF({texto} = '' OR SAFE_CAST({texto} AS FLOAT64) = {VALOR_AUSENTE}, NULL, SAFE_CAST({texto} AS FLOAT64))"


CONSULTA_FOCOS = f"""
WITH limpos AS (
  SELECT
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', TRIM(b.data_hora_gmt)) AS data_hora_gmt,
    TRIM(b.satelite) AS satelite,
    NULLIF(TRIM(b.bioma), '') AS bioma,
    {numero('b.lat')} AS lat,
    {numero('b.lon')} AS lon,
    {numero('b.numero_dias_sem_chuva')} AS numero_dias_sem_chuva,
    {numero('b.precipitacao')} AS precipitacao,
    {numero('b.risco_fogo')} AS risco_fogo,
    {numero('b.frp')} AS frp
  FROM `{TABELA_BRONZE}` AS b
  WHERE b.mes_referencia BETWEEN DATE '{MES_INICIO_TREINO}' AND DATE '{MES_TESTE}'
)
SELECT
  l.data_hora_gmt, l.satelite, s.tipo_orbita, l.bioma,
  l.lat, l.lon, l.numero_dias_sem_chuva, l.precipitacao, l.risco_fogo, l.frp
FROM limpos AS l
JOIN `{TABELA_SATELITES}` AS s USING (satelite)
WHERE l.data_hora_gmt IS NOT NULL
  AND l.frp IS NOT NULL
  AND l.lat BETWEEN {LAT_MIN} AND {LAT_MAX}
  AND l.lon BETWEEN {LON_MIN} AND {LON_MAX}
  AND (l.risco_fogo IS NULL OR l.risco_fogo BETWEEN 0 AND 1)
"""


def consultar(cliente, sql) -> pd.DataFrame:
    """Roda uma consulta com dry run antes e limite de bytes."""
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > limite:
        raise RuntimeError(f"Consulta leria mais de {LIMITE_GB_CONSULTA} GB; confira o filtro de partição.")
    print(f"Consulta vai ler {estimativa / 1024**2:,.1f} MB")
    job = cliente.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=limite))
    return job.to_dataframe()


def preparar(focos, limiares) -> pd.DataFrame:
    """Hora, mês, rótulo e conjunto (treino ou teste), como a Gold de treino vai fazer."""
    focos = focos.copy()
    focos["hora"] = focos["data_hora_gmt"].dt.hour
    focos["mes"] = focos["data_hora_gmt"].dt.month
    focos["limiar"] = focos["tipo_orbita"].map(limiares)
    if focos["limiar"].isna().any():
        faltando = sorted(focos.loc[focos["limiar"].isna(), "tipo_orbita"].unique())
        raise RuntimeError(f"Tipo de órbita sem limiar em {TABELA_LIMIAR}: {faltando}. Rode a C1 antes.")
    focos["foco_intenso"] = (focos["frp"] > focos["limiar"]).astype(int)
    inicio_teste = pd.Timestamp(MES_TESTE, tz="UTC")
    focos["conjunto"] = np.where(focos["data_hora_gmt"] < inicio_teste, "treino", "teste")
    return focos


def matriz(focos, numericas, categoricas) -> pd.DataFrame:
    """Variáveis numéricas como estão (nulos ficam NaN) e categóricas em one-hot."""
    partes = [focos[numericas].astype("float64")] if numericas else []
    partes += [pd.get_dummies(focos[c].astype("string"), prefix=c, dtype="float64") for c in categoricas]
    return pd.concat(partes, axis=1)


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
    y_treino, y_teste = treino["foco_intenso"], teste["foco_intenso"]
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
    x = matriz(focos, [], VARIAVEIS_BASELINE)
    logistica = LogisticRegression(max_iter=1000, class_weight="balanced")
    logistica.fit(x.loc[treino.index], y_treino)
    resultado["logistica"] = metricas(y_teste, logistica.predict_proba(x.loc[teste.index])[:, 1])

    # XGBoost com as variáveis do plano, e a mesma coisa sem mes
    x = matriz(focos, VARIAVEIS_NUMERICAS, VARIAVEIS_CATEGORICAS)
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
        "XGBoost local, treino de out/2025 a ago/2026 e teste em set/2026, só focos com FRP, rótulo "
        f"pelo limiar de `focos.limiar_frp`.",
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
    limiares = consultar(cliente, f"SELECT tipo_orbita, limiar FROM `{TABELA_LIMIAR}`")
    limiares = dict(zip(limiares["tipo_orbita"], limiares["limiar"].astype(float)))
    print(f"Limiares de {TABELA_LIMIAR}: " + ", ".join(f"{k} = {v:.1f} MW" for k, v in limiares.items()))

    focos = preparar(consultar(cliente, CONSULTA_FOCOS), limiares)
    print(f"{len(focos):,} focos com FRP lidos; treinando (pode levar alguns minutos)...")
    resultado = avaliar(focos)

    texto = texto_readme(resultado)
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
