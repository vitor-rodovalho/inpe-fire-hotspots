"""Testa a API no ar (Cloud Run ou local) e grava as evidências para os slides.

  1. GET /health: a API responde e diz qual modelo carregou.
  2. Paridade (C5): envia os 50 focos de model/paridade.jsonl a POST /predict
     e compara com a probabilidade do ML.PREDICT do BigQuery até a 4ª casa.
  3. Contrato: entradas inválidas devolvem 422.
  4. Latência: tempo de cada chamada, medido aqui (inclui a rede).

Só usa a biblioteca padrão, então roda em qualquer máquina. Cada execução faz
cerca de 55 requisições, dentro da cota gratuita do Cloud Run.

Uso:
    python3 api/testar_api.py https://api-foco-intenso-xxxx.run.app
    python3 api/testar_api.py https://... --gravar      # também grava docs/api_evidence.md
    python3 api/testar_api.py http://localhost:8080     # contêiner local
"""

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# =============================================================================
# Constantes
# =============================================================================
RAIZ_REPO = Path(__file__).resolve().parents[1]
ARQUIVO_PARIDADE = RAIZ_REPO / "model" / "paridade.jsonl"
ARQUIVO_EVIDENCIA = RAIZ_REPO / "docs" / "api_evidence.md"
TOLERANCIA = 5e-5 + 1e-9  # A API arredonda na 4ª casa
TEMPO_LIMITE_S = 60  # Folga para um cold start

FOCO_VALIDO = {"satelite": "NOAA-20", "data_hora_gmt": "2026-10-14T18:42:00Z", "lat": -9.51, "lon": -56.20,
               "bioma": "Amazônia", "numero_dias_sem_chuva": 21, "precipitacao": 0.0, "risco_fogo": 0.97}  # fmt: skip
INVALIDOS = [
    ("satélite desconhecido", {"satelite": "SPUTNIK-1"}),
    ("risco de fogo acima de 1", {"risco_fogo": 1.5}),
    ("coordenada fora do Brasil", {"lat": 40.0}),
    ("bioma desconhecido", {"bioma": "Savana"}),
]
# =============================================================================


def chamar(url: str, corpo: dict | None = None) -> tuple[int, dict, float]:
    """(status, corpo da resposta, milissegundos)."""
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:
            status, texto = resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        status, texto = erro.code, erro.read()
    return status, json.loads(texto or b"{}"), (time.perf_counter() - inicio) * 1000


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p / 100 * (len(ordenados) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="URL base da API, sem barra no fim")
    parser.add_argument("--gravar", action="store_true", help=f"Grava o resultado em {ARQUIVO_EVIDENCIA.name}")
    parser.add_argument("--paridade", type=Path, default=ARQUIVO_PARIDADE, help="Arquivo de paridade")
    args = parser.parse_args()
    url = args.url.rstrip("/")
    falhas = []

    status, saude, ms_primeira = chamar(f"{url}/health")
    if status != 200:
        sys.exit(f"ERRO: /health respondeu {status}: {saude}")
    print(f"1. /health em {ms_primeira:.0f} ms: modelo {saude['versao_modelo']}")

    registros = [json.loads(linha) for linha in args.paridade.read_text(encoding="utf-8").splitlines() if linha]
    tempos, iguais, maior = [], 0, 0.0
    for registro in registros:
        status, resposta, ms = chamar(f"{url}/predict", registro["foco"])
        tempos.append(ms)
        if status != 200:
            falhas.append(f"paridade {registro['id']}: status {status} {resposta}")
            continue
        diferenca = abs(resposta["probabilidade_intenso"] - registro["prob_bigquery"])
        maior = max(maior, diferenca)
        if diferenca <= TOLERANCIA and resposta["intenso"] == registro["intenso_bigquery"]:
            iguais += 1
        else:
            falhas.append(f"paridade {registro['id']}: API {resposta} x BigQuery {registro['prob_bigquery']:.6f}")
    print(f"2. Paridade: {iguais} de {len(registros)} iguais ao BigQuery até a 4ª casa (maior diferença {maior:.1e})")

    erros_ok = 0
    for nome, alteracao in INVALIDOS:
        status, _, _ = chamar(f"{url}/predict", FOCO_VALIDO | alteracao)
        erros_ok += status == 422
        if status != 422:
            falhas.append(f"contrato: {nome} devolveu {status}, esperado 422")
    print(f"3. Contrato: {erros_ok} de {len(INVALIDOS)} entradas inválidas recusadas com 422")

    mediana, p95 = statistics.median(tempos), percentil(tempos, 95)
    print(f"4. Latência de /predict ({len(tempos)} chamadas): mediana {mediana:.0f} ms, p95 {p95:.0f} ms, "
          f"máximo {max(tempos):.0f} ms")

    if args.gravar:
        ARQUIVO_EVIDENCIA.write_text("\n".join([
            "# Evidências da API (Frente D)",
            "",
            f"Gerado por `api/testar_api.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC, "
            f"contra `{url}`.",
            "",
            "| Teste | Resultado |",
            "|---|---|",
            f"| Modelo carregado (`/health`) | `{saude['versao_modelo']}` |",
            f"| Paridade com o `ML.PREDICT` (`model/paridade.jsonl`) | {iguais} de {len(registros)} iguais até a "
            f"4ª casa (maior diferença {maior:.1e}) |",
            f"| Entradas inválidas recusadas com 422 | {erros_ok} de {len(INVALIDOS)} |",
            f"| Primeira chamada (`/health`, pode incluir cold start) | {ms_primeira:.0f} ms |",
            f"| Latência de `/predict`, {len(tempos)} chamadas | mediana {mediana:.0f} ms, p95 {p95:.0f} ms, "
            f"máximo {max(tempos):.0f} ms |",
            "",
            "A latência é medida no cliente, com a rede. O tempo dentro da API vem no cabeçalho "
            "`X-Tempo-Processamento-Ms` de cada resposta.",
            "",
        ]), encoding="utf-8")
        print(f"Evidências gravadas em {ARQUIVO_EVIDENCIA.relative_to(RAIZ_REPO)}")

    if falhas:
        print("\nFALHAS:\n  " + "\n  ".join(falhas))
        sys.exit(1)
    print("\nTudo certo.")


if __name__ == "__main__":
    main()
