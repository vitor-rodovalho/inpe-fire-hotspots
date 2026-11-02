"""C6. Previsões e monitoramento: o modelo aplicado aos focos de streaming.

Cria as duas views do plano e confere se elas respondem:

  sql/gold/02_vw_previsoes.sql      cada foco de streaming com a probabilidade,
                                    a classe prevista e, se tiver FRP, o rótulo
                                    real; uso separa avaliação de estimativa
  sql/gold/03_vw_monitoramento.sql  acurácia, precisão e recall por hora de
                                    ingestão, só nos focos com FRP
  sql/demo/08_model_monitoring.sql  a consulta da demo: streaming contra o mês
                                    de teste

Os SQL são os mesmos que sql/run_sql.sh roda (com os marcadores trocados pelos
valores de config.env). Criar as views não custa nada; cada consulta a elas
roda o ML.PREDICT sobre a Silver de streaming (dezenas de MB, frações de
centavo), com dry run antes e teto de bytes. No fim, grava o resultado em
model/README.md, na seção da C6.

Uso (a partir da raiz do repositório):
    set -a; source config.env; set +a
    python3 model/previsoes_monitoramento.py               # cria as views e confere
    python3 model/previsoes_monitoramento.py --sem-readme  # só imprime
"""

import argparse
import datetime as dt
import os
import re
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

RAIZ_REPO = Path(__file__).resolve().parents[1]
VIEWS = ["sql/gold/02_vw_previsoes.sql", "sql/gold/03_vw_monitoramento.sql"]
CONSULTA_DEMO = "sql/demo/08_model_monitoring.sql"
LIMITE_GB_CONSULTA = 2
TARIFA_TIB = 6.25

CAMINHO_README = RAIZ_REPO / "model" / "README.md"
MARCA_INICIO = "<!-- C6: início (gerado por model/previsoes_monitoramento.py) -->"
MARCA_FIM = "<!-- C6: fim -->"
# =============================================================================

cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)


def renderizar(caminho) -> str:
    """O SQL com os marcadores de sql/run_sql.sh trocados pelos valores de config.env."""
    sql = (RAIZ_REPO / caminho).read_text(encoding="utf-8")
    for marcador, valor in {"PROJECT_ID": PROJECT_ID, "DATASET": DATASET, "BUCKET": BUCKET,
                            "DATA_CORTE": DATA_CORTE}.items():
        sql = sql.replace("{{" + marcador + "}}", valor)
    return sql


def consultar(sql, nome) -> tuple[pd.DataFrame, int]:
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    print(f"  {nome}: dry run {estimativa / 1024**2:,.1f} MB (US$ {estimativa / 1024**4 * TARIFA_TIB:.4f})")
    if estimativa > limite:
        raise RuntimeError(f"{nome} leria mais de {LIMITE_GB_CONSULTA} GB.")
    job = cliente.query(sql, job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=limite, labels={"frente": "c", "etapa": "c6"}))
    return job.to_dataframe(), job.total_bytes_billed or 0


def criar_views() -> None:
    for caminho in VIEWS:
        cliente.query(renderizar(caminho)).result()
        print(f"  view criada: {caminho}")


def conferir() -> dict:
    por_uso, b1 = consultar(f"""
        SELECT uso, tipo_orbita, COUNT(*) AS focos,
          AVG(probabilidade_intenso) AS prob_media,
          COUNTIF(previsto_intenso) AS previstos_intensos,
          COUNTIF(real_intenso) AS intensos_reais,
          MIN(ingerido_em) AS primeira_ingestao, MAX(ingerido_em) AS ultima_ingestao
        FROM `{PROJECT_ID}.{DATASET}.vw_previsoes`
        GROUP BY uso, tipo_orbita ORDER BY uso, tipo_orbita""", "vw_previsoes por uso")
    horas, b2 = consultar(f"SELECT * FROM `{PROJECT_ID}.{DATASET}.vw_monitoramento` ORDER BY hora_ingestao",
                          "vw_monitoramento")
    demo, b3 = consultar(renderizar(CONSULTA_DEMO), CONSULTA_DEMO)
    return {"por_uso": por_uso, "horas": horas, "demo": demo, "bytes": b1 + b2 + b3}


def numero(valor, casas=3) -> str:
    return "-" if pd.isna(valor) else f"{valor:.{casas}f}".replace(".", ",")


def texto_readme(r) -> str:
    por_uso, horas, demo = r["por_uso"], r["horas"], r["demo"]
    linhas_uso = [
        f"| {linha.uso} | {linha.tipo_orbita} | {sinal_modelo.milhar(linha.focos)} | {numero(linha.prob_media)} | "
        f"{sinal_modelo.milhar(linha.previstos_intensos)} | "
        f"{'-' if linha.uso == 'estimativa' else sinal_modelo.milhar(linha.intensos_reais)} |"
        for linha in por_uso.itertuples()
    ]
    linhas_demo = [
        f"| {linha.periodo} | {sinal_modelo.milhar(linha.focos)} | {numero(linha.acuracia)} | "
        f"{numero(linha.precisao)} | {numero(linha.recall)} |"
        for linha in demo.itertuples()
    ]
    inicio, fim = por_uso["primeira_ingestao"].min(), por_uso["ultima_ingestao"].max()
    return "\n".join([
        MARCA_INICIO,
        "## C6. Previsões e monitoramento",
        "",
        f"Gerado por `model/previsoes_monitoramento.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC. "
        "As duas views aplicam o `modelo_foco_intenso` (C4), com `ML.PREDICT`, aos focos de streaming a partir "
        f"da data de corte ({DATA_CORTE}), a cada consulta:",
        "",
        "| Arquivo | View | O que tem |",
        "|---|---|---|",
        "| `sql/gold/02_vw_previsoes.sql` | `vw_previsoes` | Cada foco com `probabilidade_intenso`, "
        "`previsto_intenso`, `real_intenso` (FRP acima do limiar da órbita) e `uso`: `avaliacao` com FRP, "
        "`estimativa` sem FRP |",
        "| `sql/gold/03_vw_monitoramento.sql` | `vw_monitoramento` | Por hora de ingestão, só com FRP: focos, "
        "intensos, previstos, acurácia, precisão e recall |",
        "| `sql/demo/08_model_monitoring.sql` | (consulta da demo) | O streaming contra o mês de teste |",
        "",
        "```bash",
        "bash sql/run_sql.sh sql/gold/02_vw_previsoes.sql sql/gold/03_vw_monitoramento.sql",
        "bash sql/run_sql.sh sql/demo/08_model_monitoring.sql",
        "```",
        "",
        f"### Resultado, com os focos de streaming já gravados ({inicio:%d/%m %H:%M} a {fim:%d/%m %H:%M} UTC)",
        "",
        "| uso | tipo_orbita | Focos | Probabilidade média | Previstos intensos | Intensos reais |",
        "|---|---|---|---|---|---|",
        *linhas_uso,
        "",
        f"A `vw_monitoramento` tem {len(horas)} horas de ingestão. Comparação com o mês de teste, com o mesmo "
        "limiar de decisão de 0,5 (`sql/demo/08_model_monitoring.sql`):",
        "",
        "| Período | Focos | Acurácia | Precisão | Recall |",
        "|---|---|---|---|---|",
        *linhas_demo,
        "",
        "Os focos sem FRP aparecem só como estimativa, separados pela coluna `uso`: não entram nas métricas e "
        "não devem ser somados aos medidos.",
        "",
        f"As três consultas leram {r['bytes'] / 1024**2:,.0f} MB (US$ {numero(r['bytes'] / 1024**4 * TARIFA_TIB, 4)}).",
        "",
        "### Pronto quando",
        "",
        "As duas views respondem sobre os focos já gravados. Como o `ML.PREDICT` roda a cada consulta, os "
        "números mudam sozinhos quando o Dataflow grava focos novos; isso se confirma no ensaio, com o replay e "
        "o job ligados (`sql/demo/08_model_monitoring.sql` mostra a última hora mudando).",
        MARCA_FIM,
    ])


def atualizar_readme(texto) -> None:
    atual = CAMINHO_README.read_text(encoding="utf-8")
    padrao = re.compile(re.escape(MARCA_INICIO) + r".*?" + re.escape(MARCA_FIM), re.DOTALL)
    if padrao.search(atual):
        novo = padrao.sub(lambda _m: texto, atual)
    else:   # Logo depois da C5, antes dos custos
        i = atual.index("\n## Custos no GCP")
        novo = atual[:i].rstrip("\n") + "\n\n" + texto + "\n" + atual[i:]
    CAMINHO_README.write_text(novo.rstrip("\n") + "\n", encoding="utf-8")
    print(f"\nResultado gravado em {CAMINHO_README}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-readme", action="store_true", help="Só imprime o resultado")
    args = parser.parse_args()

    print("Criando as views:")
    criar_views()
    print("\nConferindo:")
    texto = texto_readme(conferir())
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
