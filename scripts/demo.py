"""Demo da API na apresentação (D6): três chamadas a POST /predict.

  1. Foco com FRP que acabou de chegar pelo streaming: a previsão ao lado do
     rótulo real (FRP acima do limiar da órbita). É o monitoramento.
  2. Foco sem FRP que acabou de chegar (satélite que não mede): a previsão é a
     única estimativa de intensidade que existe para ele (justificativa 1).
  3. Foco hipotético, escrito à mão: "se surgir um foco aqui, agora, com este
     clima, qual a chance de ser intenso?" (justificativa 2).

Os focos 1 e 2 são os mais recentes de silver_focos_streaming (lidos só das
partições a partir de DATA_CORTE, com dry run e teto de bytes). Com --offline,
usa focos fixos e não consulta o BigQuery: é o plano B se a consulta falhar.

Uso (a partir da raiz do repositório, com config.env carregado):
    set -a; source config.env; set +a
    python3 scripts/demo.py                     # URL do Cloud Run descoberta pelo gcloud
    python3 scripts/demo.py https://...run.app
    python3 scripts/demo.py --offline
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# =============================================================================
# Constantes. Os valores vêm de config.env
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
DATASET = os.environ.get("DATASET", "focos")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATA_CORTE = os.environ.get("DATA_CORTE", "2026-10-01")
SERVICO = os.environ.get("CLOUD_RUN_SERVICO", "api-foco-intenso")
TETO_BYTES = 1024**3
CAMPOS = ("satelite", "data_hora_gmt", "lat", "lon", "bioma", "numero_dias_sem_chuva", "precipitacao", "risco_fogo")

HIPOTETICO = {
    "satelite": "GOES-19", "data_hora_gmt": "2026-10-23T17:00:00Z", "lat": -12.55, "lon": -55.72,
    "bioma": "Cerrado", "numero_dias_sem_chuva": 30, "precipitacao": 0.0, "risco_fogo": 1.0,
}  # fmt: skip
# Plano B (--offline): focos com o formato da Silver de streaming
OFFLINE_COM_FRP = {
    "id": "exemplo-com-frp", "frp": 54.3, "limiar": 28.4, "satelite": "NOAA-20",
    "data_hora_gmt": "2026-10-14T17:30:00Z", "lat": -9.51, "lon": -56.20, "bioma": "Amazônia",
    "numero_dias_sem_chuva": 21, "precipitacao": 0.0, "risco_fogo": 0.97,
}  # fmt: skip
OFFLINE_SEM_FRP = {
    "id": "exemplo-sem-frp", "frp": None, "limiar": None, "satelite": "MSG-03",
    "data_hora_gmt": "2026-10-14T13:10:00Z", "lat": -15.20, "lon": -47.80, "bioma": "Cerrado",
    "numero_dias_sem_chuva": 12, "precipitacao": 0.2, "risco_fogo": 0.65,
}  # fmt: skip
# =============================================================================


def url_cloud_run() -> str:
    comando = ["gcloud", "run", "services", "describe", SERVICO, f"--region={REGIAO}", "--format=value(status.url)"]
    return subprocess.run(comando, check=True, capture_output=True, text=True, shell=os.name == "nt").stdout.strip()


def focos_recentes() -> tuple[dict, dict]:
    """O foco com FRP e o sem FRP ingeridos por último no streaming."""
    from google.cloud import bigquery

    sql = f"""
    SELECT * EXCEPT (n) FROM (
      SELECT f.id, f.frp, l.limiar, f.satelite, f.data_hora_gmt, f.lat, f.lon, f.bioma,
             f.numero_dias_sem_chuva, f.precipitacao, f.risco_fogo, f.ingerido_em,
             ROW_NUMBER() OVER (PARTITION BY f.frp IS NULL ORDER BY f.ingerido_em DESC) AS n
      FROM `{PROJECT_ID}.{DATASET}.silver_focos_streaming` AS f
      JOIN `{PROJECT_ID}.{DATASET}.satelites` AS s USING (satelite)
      LEFT JOIN `{PROJECT_ID}.{DATASET}.limiar_frp` AS l USING (tipo_orbita)
      WHERE f.data_deteccao >= DATE '{DATA_CORTE}'
        AND (f.risco_fogo IS NULL OR f.risco_fogo BETWEEN 0 AND 1)
        AND (f.bioma IS NULL OR f.bioma IN ('Amazônia', 'Caatinga', 'Cerrado', 'Mata Atlântica', 'Pampa', 'Pantanal'))
    ) WHERE n = 1
    """
    cliente = bigquery.Client(project=PROJECT_ID)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > TETO_BYTES:
        sys.exit(f"ERRO: a consulta leria {estimativa / 1024**2:,.0f} MB. Use --offline.")
    linhas = [dict(linha) for linha in cliente.query(
        sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=TETO_BYTES)).result()]  # fmt: skip
    print(f"(consulta ao BigQuery: {estimativa / 1024**2:,.1f} MB lidos)\n")
    com_frp = next((linha for linha in linhas if linha["frp"] is not None), None)
    sem_frp = next((linha for linha in linhas if linha["frp"] is None), None)
    if com_frp is None or sem_frp is None:
        sys.exit("ERRO: a Silver de streaming não tem focos com e sem FRP. O replay está ligado? Use --offline.")
    for linha in (com_frp, sem_frp):
        linha["data_hora_gmt"] = linha["data_hora_gmt"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return com_frp, sem_frp


def prever(url: str, foco: dict) -> tuple[dict, float]:
    corpo = json.dumps({campo: foco[campo] for campo in CAMPOS}).encode("utf-8")
    pedido = urllib.request.Request(f"{url}/predict", data=corpo, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            return json.loads(resposta.read()), (time.perf_counter() - inicio) * 1000
    except urllib.error.HTTPError as erro:
        sys.exit(f"ERRO {erro.code} da API: {erro.read().decode()}")


def mostrar(numero: int, titulo: str, foco: dict, resposta: dict, ms: float, real: str | None) -> None:
    clima = (f"{foco['numero_dias_sem_chuva']} dias sem chuva, precipitação {foco['precipitacao']}, "
             f"risco de fogo {foco['risco_fogo']}")  # fmt: skip
    print(f"{numero}. {titulo}")
    print(f"   Foco:      {foco['satelite']}, {foco['data_hora_gmt']}, ({foco['lat']}, {foco['lon']}), "
          f"{foco['bioma'] or 'sem bioma'}")  # fmt: skip
    print(f"   Clima:     {clima}")
    print(f"   Previsão:  {resposta['probabilidade_intenso']:.1%} de ser intenso -> "
          f"{'INTENSO' if resposta['intenso'] else 'não intenso'}")  # fmt: skip
    if real:
        print(f"   Real:      {real}")
    print(f"   Resposta:  {ms:.0f} ms, modelo {resposta['versao_modelo']}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", help="URL da API; sem ela, pergunta ao gcloud")
    parser.add_argument("--offline", action="store_true", help="Focos fixos, sem consultar o BigQuery")
    args = parser.parse_args()
    url = (args.url or url_cloud_run()).rstrip("/")
    print(f"API: {url}\n")

    com_frp, sem_frp = (OFFLINE_COM_FRP, OFFLINE_SEM_FRP) if args.offline else focos_recentes()
    origem = "exemplo fixo" if args.offline else "acabou de chegar pelo streaming"

    resposta, ms = prever(url, com_frp)
    real_intenso = com_frp["limiar"] is not None and com_frp["frp"] > com_frp["limiar"]
    real = (f"FRP {com_frp['frp']:.1f} MW, limiar {com_frp['limiar']:.1f} MW -> "
            f"{'INTENSO' if real_intenso else 'não intenso'} "
            f"({'acertou' if real_intenso == resposta['intenso'] else 'errou'})")  # fmt: skip
    mostrar(1, f"Foco com FRP ({origem}): previsão contra o real", com_frp, resposta, ms, real)

    resposta, ms = prever(url, sem_frp)
    mostrar(2, f"Foco sem FRP ({origem}): a estimativa é a única informação de intensidade", sem_frp,
            resposta, ms, f"sem FRP: o satélite {sem_frp['satelite']} não mede a intensidade")

    resposta, ms = prever(url, HIPOTETICO)
    mostrar(3, "Foco hipotético: e se surgir um foco aqui, agora, com este clima?", HIPOTETICO, resposta, ms, None)


if __name__ == "__main__":
    main()
