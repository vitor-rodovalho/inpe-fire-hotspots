#!/usr/bin/env bash
# Funções e carregamento de configuração usados por todos os scripts de infra.
# Não execute este arquivo diretamente: os outros scripts fazem "source" dele.

set -euo pipefail

RAIZ_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Carrega config.env (obrigatório) e config.local.env (opcional, pessoal)
set -a
# shellcheck disable=SC1091
source "${RAIZ_REPO}/config.env"
if [[ -f "${RAIZ_REPO}/config.local.env" ]]; then
  # shellcheck disable=SC1091
  source "${RAIZ_REPO}/config.local.env"
fi
set +a

# Nomes derivados (não precisam ser editados)
SA_DATAFLOW_EMAIL="${SA_DATAFLOW}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_API_EMAIL="${SA_API}@${PROJECT_ID}.iam.gserviceaccount.com"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

exigir_variavel() {
  local nome="$1"
  if [[ -z "${!nome:-}" ]]; then
    echo "ERRO: defina ${nome} em config.local.env (veja config.local.env.example)." >&2
    exit 1
  fi
}

# Garante que todos os comandos gcloud usem o projeto da configuração
gcloud config set project "${PROJECT_ID}" >/dev/null 2>&1 || true
