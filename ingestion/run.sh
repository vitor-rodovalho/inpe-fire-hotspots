#!/usr/bin/env bash
# Carrega config.env e roda um dos scripts de ingestão, repassando os argumentos.
#
# Uso:
#   bash ingestion/run.sh download_inpe [--tipo mensal|diario|todos] [--destino PASTA] [opções]
#   bash ingestion/run.sh replay_pubsub --inicio AAAA-MM-DD [--fim AAAA-MM-DD] [--saida ARQUIVO] [opções]
source "$(dirname "$0")/../infra/common.sh"

SCRIPT="${1:-}"
if [[ -z "${SCRIPT}" ]]; then
  echo "Uso: bash ingestion/run.sh <download_inpe|replay_pubsub> [argumentos]" >&2
  exit 1
fi
shift

python3 "${RAIZ_REPO}/ingestion/${SCRIPT%.py}.py" "$@"
