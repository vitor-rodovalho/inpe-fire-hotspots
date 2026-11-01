"""Cliente mínimo da API, usado por api/testar_api.py e scripts/demo.py.

Só usa a biblioteca padrão (mais o gcloud, se estiver instalado), para rodar no
Cloud Shell ou em qualquer máquina sem instalar nada.

O token é procurado, nesta ordem:
  1. variável de ambiente API_TOKEN;
  2. linha API_TOKEN= do config.local.env (fora do Git);
  3. variável API_TOKEN do serviço no Cloud Run, lida pelo gcloud (para um
     colega rodar a demo sem copiar o token à mão).
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

# =============================================================================
# Constantes. Os valores vêm de config.env
# =============================================================================
RAIZ_REPO = Path(__file__).resolve().parents[1]
CONFIG_LOCAL = RAIZ_REPO / "config.local.env"
SERVICO = os.environ.get("CLOUD_RUN_SERVICO", "api-foco-intenso")
REGIAO = os.environ.get("REGIAO", "us-central1")
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
TEMPO_LIMITE_S = 60  # Folga para um cold start
# =============================================================================


def _gcloud(*argumentos: str) -> str:
    comando = ["gcloud", *argumentos, f"--project={PROJECT_ID}"]
    return subprocess.run(comando, check=True, capture_output=True, text=True, shell=os.name == "nt").stdout


def url_cloud_run() -> str:
    return _gcloud("run", "services", "describe", SERVICO, f"--region={REGIAO}", "--format=value(status.url)").strip()


def ler_token() -> str:
    if os.environ.get("API_TOKEN"):
        return os.environ["API_TOKEN"]
    if CONFIG_LOCAL.exists():
        for linha in CONFIG_LOCAL.read_text(encoding="utf-8").splitlines():
            if linha.startswith("API_TOKEN=") and linha.split("=", 1)[1].strip():
                return linha.split("=", 1)[1].strip().strip('"')
    try:
        servico = json.loads(_gcloud("run", "services", "describe", SERVICO, f"--region={REGIAO}", "--format=json"))
        variaveis = servico["spec"]["template"]["spec"]["containers"][0].get("env", [])
        return next(v["value"] for v in variaveis if v["name"] == "API_TOKEN")
    except (OSError, subprocess.CalledProcessError, StopIteration, KeyError, json.JSONDecodeError):
        return ""


def chamar(url: str, corpo: dict | None = None, token: str | None = None) -> tuple[int, dict, float]:
    """(status, corpo da resposta, milissegundos). Com corpo, faz POST."""
    cabecalhos = {"Content-Type": "application/json"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos)
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:
            status, texto = resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        status, texto = erro.code, erro.read()
    return status, json.loads(texto or b"{}"), (time.perf_counter() - inicio) * 1000
