"""C4. Treino e avaliação: o boosted tree do BigQuery ML na Gold e os baselines no mês de teste.

Roda os SQL de sql/modelo/, os mesmos que sql/run_sql.sh roda (com os
marcadores trocados pelos valores de config.env), e grava as métricas em
docs/model_metrics.md:

  01_modelo_foco_intenso.sql  CREATE MODEL do plano, com o registro no Vertex AI
  02_baseline_logistica.sql   baseline B: regressão logística com tipo_orbita e hora
  03_avaliacao.sql            ML.EVALUATE do modelo e dos baselines em set/2026
  04_roc_curve.sql            ML.ROC_CURVE do modelo em set/2026

Antes de cada treino, o dry run mostra os bytes estimados (o plano pede), e
nada roda com --so-estimar. Cada CREATE MODEL tem teto de bytes e é cancelado
depois de LIMITE_MINUTOS. No fim, confere se o modelo aparece no Vertex AI
Model Registry.

Uso (a partir da raiz do repositório):
    pip install -r model/requirements.txt
    set -a; source config.env; set +a
    python3 model/treino_avaliacao.py --so-estimar   # só os dry runs
    python3 model/treino_avaliacao.py                # treina, avalia e grava docs/model_metrics.md
    python3 model/treino_avaliacao.py --so-avaliar   # só 03 e 04, com os modelos já treinados
    python3 model/treino_avaliacao.py --treinar 02_baseline_logistica.sql   # treina só um

Os jobs de treino ficam em dados/c4/treinos.json, para que o docs mostre o
último treino de cada modelo mesmo quando só um é refeito.
"""

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

import sinal_modelo

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")
DATA_CORTE = os.environ.get("DATA_CORTE", "2026-10-01")
BUCKET = os.environ.get("BUCKET", f"{PROJECT_ID}-data")
VERTEX_MODEL_ID = "modelo_foco_intenso"

RAIZ_REPO = Path(__file__).resolve().parents[1]
PASTA_SQL = RAIZ_REPO / "sql" / "modelo"
CAMINHO_DOCS = RAIZ_REPO / "docs" / "model_metrics.md"
ARQUIVO_TREINOS = RAIZ_REPO / "dados" / "c4" / "treinos.json"

# Arquivo: (tarifa em US$ por TiB, teto de bytes faturados em GiB)
TREINOS = {
    "01_modelo_foco_intenso.sql": (6.25, 300),     # Externo: pré-processamento + Vertex AI
    "02_baseline_logistica.sql": (312.50, 5),      # Interno: US$ 1,53 no teto
}
TARIFA_CONSULTA = 6.25
LIMITE_GB_CONSULTA = 2
LIMITE_MINUTOS = 120
INTERVALO_SEGUNDOS = 30

ALVO_AUC = sinal_modelo.ALVO_AUC                    # 0,70, critério do plano
MARGEM_SOBRE_BASELINE = sinal_modelo.MARGEM_SOBRE_BASELINE
LIMIARES_TABELA = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]    # Linhas da curva ROC no docs
# =============================================================================

cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)


def renderizar(nome) -> str:
    """O SQL com os marcadores de sql/run_sql.sh trocados pelos valores de config.env."""
    sql = (PASTA_SQL / nome).read_text(encoding="utf-8")
    for marcador, valor in {"PROJECT_ID": PROJECT_ID, "DATASET": DATASET, "BUCKET": BUCKET,
                            "DATA_CORTE": DATA_CORTE}.items():
        sql = sql.replace("{{" + marcador + "}}", valor)
    return sql


def gib(valor) -> float:
    return (valor or 0) / 1024**3


def estimar(nome) -> int:
    sql = renderizar(nome)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    tarifa = TREINOS.get(nome, (TARIFA_CONSULTA, None))[0]
    print(f"  {nome}: dry run {estimativa / 1024**2:,.1f} MiB, US$ {gib(estimativa) / 1024 * tarifa:.4f} "
          f"na tarifa de US$ {tarifa:.2f} por TiB")
    return estimativa


def treinar(nome) -> dict:
    """CREATE MODEL com teto de bytes, acompanhando até o fim ou até LIMITE_MINUTOS."""
    tarifa, teto_gib = TREINOS[nome]
    estimar(nome)
    config = bigquery.QueryJobConfig(maximum_bytes_billed=int(teto_gib * 1024**3),
                                     labels={"frente": "c", "etapa": "c4"})
    job = cliente.query(renderizar(nome), job_config=config)
    inicio = time.monotonic()
    print(f"  job {job.job_id}: teto {teto_gib} GiB, cancela em {LIMITE_MINUTOS} min")
    while not job.done(reload=True):
        minutos = (time.monotonic() - inicio) / 60
        if minutos > LIMITE_MINUTOS:
            job.cancel()
            raise RuntimeError(f"{nome} cancelado depois de {minutos:.0f} min; confira o faturamento.")
        print(f"    {minutos:5.1f} min, {job.state}", flush=True)
        time.sleep(INTERVALO_SEGUNDOS)
    if job.error_result:
        raise RuntimeError(f"{nome} falhou: {job.error_result}")
    resultado = {"arquivo": nome, "job_id": job.job_id, "segundos": (job.ended - job.started).total_seconds(),
                 "bytes_faturados": job.total_bytes_billed or 0}
    resultado["dolares"] = gib(resultado["bytes_faturados"]) / 1024 * tarifa
    print(f"  fim: {resultado['segundos'] / 60:.1f} min, {gib(resultado['bytes_faturados']):.1f} GiB "
          f"(US$ {resultado['dolares']:.2f})")
    return resultado


def consultar(nome) -> pd.DataFrame:
    """Consulta de sql/modelo/ com dry run antes e maximum_bytes_billed."""
    estimativa = estimar(nome)
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    if estimativa > limite:
        raise RuntimeError(f"{nome} leria mais de {LIMITE_GB_CONSULTA} GB.")
    return cliente.query(renderizar(nome), job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=limite, labels={"frente": "c", "etapa": "c4"})).to_dataframe()


def info_modelo() -> dict:
    """Iterações e registro no Vertex AI do modelo treinado."""
    import google.auth
    import google.auth.transport.requests

    modelo = cliente.get_model(f"{PROJECT_ID}.{DATASET}.modelo_foco_intenso")
    iteracoes = cliente.query(
        f"SELECT COUNT(*) AS n, SUM(duration_ms) AS ms FROM "
        f"ML.TRAINING_INFO(MODEL `{PROJECT_ID}.{DATASET}.modelo_foco_intenso`)").to_dataframe()
    credenciais, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    sessao = google.auth.transport.requests.AuthorizedSession(credenciais)
    url = f"https://{REGIAO}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{REGIAO}/models"
    resposta = sessao.get(url, params={"filter": f'display_name="{VERTEX_MODEL_ID}"'})
    registros = resposta.json().get("models", []) if resposta.ok else []
    return {
        "criado_em": modelo.created, "iteracoes": int(iteracoes.n[0]),
        "segundos_treino": int(iteracoes.ms[0] or 0) / 1000,
        "vertex": [{"id": r["name"].split("/")[-1], "versao": r.get("versionId"),
                    "aliases": r.get("versionAliases", [])} for r in registros],
        "vertex_erro": None if resposta.ok else resposta.text[:200],
    }


def texto_docs(metricas, roc, info, treinos) -> str:
    def numero(valor, casas=3):
        return "-" if pd.isna(valor) else f"{valor:.{casas}f}".replace(".", ",")

    por_modelo = metricas.set_index("modelo")
    auc = por_modelo.loc["modelo_foco_intenso", "roc_auc_exato"]
    auc_logistica = por_modelo.loc["baseline_logistica", "roc_auc_exato"]
    ganho = auc - auc_logistica
    acuracia = por_modelo.loc["modelo_foco_intenso", "accuracy"]
    acuracia_a = por_modelo.loc["baseline_majoritaria", "accuracy"]
    passou = auc >= ALVO_AUC and ganho >= MARGEM_SOBRE_BASELINE
    nomes = {"modelo_foco_intenso": "Modelo (boosted tree)",
             "baseline_logistica": "Baseline B: regressão logística (`tipo_orbita`, `hora`)",
             "baseline_majoritaria": "Baseline A: sempre a classe majoritária"}

    linhas_roc = []
    for alvo in LIMIARES_TABELA:
        linha = roc.iloc[(roc["limiar"] - alvo).abs().argsort()[:1]].iloc[0]
        linhas_roc.append(f"| {numero(linha.limiar, 2)} | {numero(linha.precisao)} | {numero(linha.recall)} | "
                          f"{numero(linha.taxa_falsos_positivos)} |")

    custo_total = sum(t["dolares"] for t in treinos)
    vertex = "; ".join(f"`{VERTEX_MODEL_ID}` versão {v['versao']} ({', '.join(v['aliases']) or 'sem alias'})"
                       for v in info["vertex"]) or f"**não encontrado** ({info['vertex_erro'] or 'lista vazia'})"
    return "\n".join([
        "# Métricas do modelo (C4)",
        "",
        f"Gerado por `model/treino_avaliacao.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC, "
        "a partir dos SQL de `sql/modelo/`. O modelo é o boosted tree do BigQuery ML do plano "
        "(`focos.modelo_foco_intenso`), treinado nos focos de treino da `gold_treino` (out/2025 a ago/2026) e "
        "avaliado no mês de teste (set/2026), com os dois baselines nos mesmos focos.",
        "",
        "## Resultado no mês de teste",
        "",
        "| Modelo | ROC AUC | ROC AUC do `ML.EVALUATE` | Precisão | Recall | Acurácia | F1 |",
        "|---|---|---|---|---|---|---|",
        *[f"| {nomes[m]} | {numero(r.roc_auc_exato)} | {numero(r.roc_auc)} | {numero(r.precision)} | "
          f"{numero(r.recall)} | {numero(r.accuracy)} | {numero(r.f1_score)} |" for m, r in por_modelo.iterrows()],
        "",
        "A coluna ROC AUC traz o valor exato, calculado a partir do `ML.PREDICT` em `sql/modelo/03_avaliacao.sql`. "
        "O do `ML.EVALUATE` é aproximado e erra quando muitos focos recebem a mesma probabilidade: é o caso da "
        "regressão logística, que só tem 47 valores distintos. No boosted tree, os dois coincidem.",
        "",
        f"**Critério do plano:** ROC AUC de pelo menos {numero(ALVO_AUC, 2)} e ganhar claramente da regressão "
        f"logística. O modelo tem {numero(auc)}, {numero(ganho)} acima dela: "
        f"{'passou' if passou else '**não passou**'}. Para comparar, o XGBoost local da C2, com a mesma Gold, "
        "teve 0,725.",
        "",
        "Precisão, recall, acurácia e F1 usam o limiar de decisão de 0,5. Com `auto_class_weights`, a "
        "probabilidade não é calibrada e esse limiar marca mais intensos do que existem"
        + (": a acurácia fica abaixo da do baseline A, que acerta os não intensos sem aprender nada"
           if acuracia < acuracia_a else "")
        + ". Por isso o critério é o ROC AUC.",
        "",
        "## Curva ROC (`ML.ROC_CURVE`)",
        "",
        "Precisão e recall dos intensos em alguns limiares de decisão:",
        "",
        "| Limiar | Precisão | Recall | Taxa de falsos positivos |",
        "|---|---|---|---|",
        *linhas_roc,
        "",
        "## Treino e registro",
        "",
        f"- **Modelo:** `focos.modelo_foco_intenso`, criado em {info['criado_em']:%d/%m/%Y %H:%M} UTC, "
        f"{info['iteracoes']} iterações ({info['segundos_treino'] / 60:.0f} minutos de treino informados pelo "
        "modelo), com as opções do plano e os hiperparâmetros da C2 (`NO_SPLIT`, profundidade 6, taxa de "
        "aprendizado 0,1, subamostragem de 0,8 nas linhas e nas colunas).",
        f"- **Vertex AI Model Registry:** {vertex}.",
        *[f"- **Job de `{t['arquivo']}`:** {t['segundos'] / 60:.0f} minutos, "
          f"{numero(gib(t['bytes_faturados']), 1)} GiB faturados (US$ {numero(t['dolares'], 2)})." for t in treinos],
        *([f"- **Custo dos treinos:** US$ {numero(custo_total, 2)}, dentro de 1 TiB grátis por mês."]
          if treinos else []),
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--so-estimar", action="store_true", help="Só os dry runs dos treinos")
    parser.add_argument("--so-avaliar", action="store_true", help="Não treina; avalia os modelos que existem")
    parser.add_argument("--treinar", nargs="+", choices=list(TREINOS), help="Treina só estes arquivos")
    args = parser.parse_args()

    if args.so_estimar:
        print("Dry run dos treinos:")
        for nome in TREINOS:
            estimar(nome)
        return

    treinos = json.loads(ARQUIVO_TREINOS.read_text(encoding="utf-8")) if ARQUIVO_TREINOS.exists() else {}
    if not args.so_avaliar:
        for nome in args.treinar or TREINOS:
            print(f"\nTreino: {nome}")
            treinos[nome] = treinar(nome)
            ARQUIVO_TREINOS.parent.mkdir(parents=True, exist_ok=True)
            ARQUIVO_TREINOS.write_text(json.dumps(treinos, indent=2), encoding="utf-8")

    print("\nAvaliação no mês de teste:")
    metricas = consultar("03_avaliacao.sql")
    print(metricas.to_string(index=False))
    roc = consultar("04_roc_curve.sql")
    texto = texto_docs(metricas, roc, info_modelo(), [treinos[n] for n in TREINOS if n in treinos])
    CAMINHO_DOCS.write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"Métricas gravadas em {CAMINHO_DOCS}")


if __name__ == "__main__":
    main()
