"""C1. Exploração e limiar: distribuição do FRP e limiar de "foco intenso" por tipo de órbita.

Lê da Silver histórica (A5) só os meses de treino (out/2025 a ago/2026) e só
as colunas satelite e frp. A Silver já trata vazio e -999 como nulo, com as
mesmas regras do streaming. O tipo de órbita vem de focos.satelites, a mesma
tabela que o pipeline e a API usam, para que os nomes ('geoestacionario',
'polar') casem nas três pontas.

No pandas, o script mostra:
  1. a parcela de focos sem FRP, por tipo de órbita e por satélite, ao lado da
     parcela do resumo de A1 (docs/data_profile.md);
  2. a distribuição do FRP (percentis), por tipo de órbita e por satélite;
  3. o limiar proposto: o percentil escolhido (90, pelo plano) de cada órbita,
     comparado com os candidatos do notebook 01.

Por padrão nada é gravado. Depois de decidir o valor, rode com --gravar para
substituir focos.limiar_frp, no esquema de docs/contracts.md
(tipo_orbita, limiar, percentil, calculado_em). A tabela é lida pela Gold de
treino (A7) e pelo Dataflow (B4), que só a lê ao subir: avise as Frentes A e B.

Uso (a partir da raiz do repositório):
    pip install -r model/requirements.txt
    set -a; source config.env; set +a
    python3 model/exploracao_limiar.py                   # exploração, sem gravar
    python3 model/exploracao_limiar.py --percentil 95    # outro limiar, sem gravar
    python3 model/exploracao_limiar.py --gravar          # grava o P90 em focos.limiar_frp
"""

import argparse
import datetime as dt
import os

import pandas as pd
from google.cloud import bigquery

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")

TABELA_SILVER = f"{PROJECT_ID}.{DATASET}.silver_focos_historico"
TABELA_SATELITES = f"{PROJECT_ID}.{DATASET}.satelites"
TABELA_LIMIAR = f"{PROJECT_ID}.{DATASET}.limiar_frp"

INICIO_TREINO = "2025-10-01"       # Meses de treino (partição data_deteccao da Silver)
FIM_TREINO = "2026-08-31"          # Set/2026 é o mês de teste e fica de fora
PERCENTIL_LIMIAR = 90              # Proposta do plano para "foco intenso"
PERCENTIS_DISTRIBUICAO = [50, 75, 90, 95, 99]   # Os mesmos do notebook 01
LIMITE_GB_CONSULTA = 2
PCT_SEM_FRP_A1 = 1.7               # Resumo de A1 (docs/data_profile.md), nos 12 meses do histórico

# Valores candidatos do notebook 01 (P90 com APPROX_QUANTILES no BigQuery), para conferência
CANDIDATOS_MW = {"geoestacionario": 202.2, "polar": 28.4}
TOLERANCIA_MW = 1.0
# =============================================================================

CONSULTA_FRP = f"""
SELECT s.tipo_orbita, f.satelite, f.frp
FROM `{TABELA_SILVER}` AS f
LEFT JOIN `{TABELA_SATELITES}` AS s USING (satelite)
WHERE f.data_deteccao BETWEEN DATE '{INICIO_TREINO}' AND DATE '{FIM_TREINO}'
"""


def ler_focos_treino(cliente) -> pd.DataFrame:
    """Focos dos meses de treino com tipo de órbita e FRP, com dry run antes."""
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(CONSULTA_FRP, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    print(f"Consulta vai ler {estimativa / 1024**2:,.1f} MB da Silver histórica")
    if estimativa > limite:
        raise RuntimeError(f"Consulta leria mais de {LIMITE_GB_CONSULTA} GB; confira o filtro de partição.")
    job = cliente.query(CONSULTA_FRP, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=limite))
    return job.to_dataframe()


def parcela_sem_frp(focos, chaves) -> pd.DataFrame:
    """Focos, focos com FRP e % sem FRP por grupo."""
    tabela = focos.groupby(chaves).agg(focos=("frp", "size"), com_frp=("frp", "count"))
    tabela["pct_sem_frp"] = (100 * (1 - tabela["com_frp"] / tabela["focos"])).round(1)
    return tabela


def distribuicao_frp(focos, chaves) -> pd.DataFrame:
    """Percentis do FRP por grupo, só nos focos com FRP."""
    com_frp = focos.dropna(subset=["frp"])
    tabela = com_frp.groupby(chaves)["frp"].quantile([p / 100 for p in PERCENTIS_DISTRIBUICAO]).unstack()
    tabela.columns = [f"p{p}" for p in PERCENTIS_DISTRIBUICAO]
    tabela["frp_max"] = com_frp.groupby(chaves)["frp"].max()
    return tabela.round(1)


def calcular_limiares(focos, percentil) -> pd.DataFrame:
    """Limiar por tipo de órbita, no esquema do contrato (tipo_orbita, limiar, percentil, calculado_em)."""
    com_frp = focos.dropna(subset=["frp"])
    limiares = com_frp.groupby("tipo_orbita")["frp"].quantile(percentil / 100).rename("limiar").reset_index()
    limiares["tipo_orbita"] = limiares["tipo_orbita"].astype("string")
    limiares["limiar"] = limiares["limiar"].astype("float64")
    limiares["percentil"] = percentil
    limiares["calculado_em"] = pd.Timestamp(dt.datetime.now(dt.timezone.utc))
    return limiares


def imprimir_exploracao(focos, limiares, percentil) -> None:
    pct_sem_frp = 100 * focos["frp"].isna().mean()
    print(f"\n1. Focos sem FRP nos meses de treino: {pct_sem_frp:.1f}% "
          f"(A1, nos 12 meses do histórico: {PCT_SEM_FRP_A1}%). Por tipo de órbita:")
    print(parcela_sem_frp(focos, "tipo_orbita").to_string())
    print("\n   ... e por satélite:")
    print(parcela_sem_frp(focos, ["tipo_orbita", "satelite"]).to_string())

    print("\n2. Distribuição do FRP (MW), focos com FRP, por tipo de órbita:")
    print(distribuicao_frp(focos, "tipo_orbita").to_string())
    print("\n   ... e por satélite (sensores da mesma órbita podem medir energias diferentes por pixel):")
    print(distribuicao_frp(focos, ["tipo_orbita", "satelite"]).to_string())

    print(f"\n3. Limiar proposto (P{percentil} do FRP nos meses de treino), em MW:")
    com_frp = focos.dropna(subset=["frp"]).merge(limiares[["tipo_orbita", "limiar"]], on="tipo_orbita")
    pct_intensos = (100 * (com_frp["frp"] > com_frp["limiar"])).groupby(com_frp["satelite"]).mean().round(1)
    for linha in limiares.itertuples():
        candidato = CANDIDATOS_MW.get(linha.tipo_orbita)
        if percentil == PERCENTIL_LIMIAR and candidato is not None:
            situacao = "confere" if abs(linha.limiar - candidato) <= TOLERANCIA_MW else "DIFERENTE"
            comparacao = f"   candidato {candidato}  [{situacao}]"
        else:
            comparacao = ""
        print(f"  {linha.tipo_orbita:<16} {linha.limiar:8.1f}{comparacao}")
    print("\n   % de focos com FRP que seriam intensos, por satélite:")
    print(pct_intensos.to_string())


def gravar_limiares(cliente, limiares) -> None:
    """Substitui focos.limiar_frp, mantendo o esquema de sql/reference/02_limiar_frp.sql."""
    config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("tipo_orbita", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("limiar", "FLOAT64", mode="REQUIRED",
                                 description="FRP em MW acima do qual o foco é intenso"),
            bigquery.SchemaField("percentil", "INT64",
                                 description="Percentil usado no cálculo, por exemplo 90"),
            bigquery.SchemaField("calculado_em", "TIMESTAMP"),
        ],
    )
    cliente.load_table_from_dataframe(limiares, TABELA_LIMIAR, job_config=config).result()
    print(f"\n{len(limiares)} linhas gravadas em {TABELA_LIMIAR}.")
    print("Avise a Frente A (rótulo da Gold de treino, A7) e a Frente B, que precisa drenar e subir "
          "o Dataflow de novo para preencher qtd_intensos (B4).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--percentil", type=int, default=PERCENTIL_LIMIAR,
                        help=f"Percentil do FRP usado como limiar (padrão: {PERCENTIL_LIMIAR})")
    parser.add_argument("--gravar", action="store_true", help="Substitui focos.limiar_frp pelo limiar calculado")
    args = parser.parse_args()

    cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)
    focos = ler_focos_treino(cliente)

    sem_orbita = sorted(focos.loc[focos["tipo_orbita"].isna(), "satelite"].unique())
    if sem_orbita:
        raise RuntimeError(f"Satélites sem tipo de órbita em {TABELA_SATELITES}: {sem_orbita}. "
                           "Rode sql/reference/01_satelites.sql de novo.")

    limiares = calcular_limiares(focos, args.percentil)
    imprimir_exploracao(focos, limiares, args.percentil)

    if not args.gravar:
        print("\nNada foi gravado. Depois de decidir o limiar, rode de novo com --gravar.")
        return
    gravar_limiares(cliente, limiares)


if __name__ == "__main__":
    main()
