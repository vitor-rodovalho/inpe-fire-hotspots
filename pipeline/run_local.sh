#!/usr/bin/env bash
# Roda o pipeline na sua máquina (DirectRunner). Dois modos:
#
#   bash pipeline/run_local.sh
#       Lê a assinatura real do Pub/Sub e grava nas tabelas reais do BigQuery.
#       Custo quase zero, mas os focos do teste ficam nas tabelas. Ctrl+C encerra.
#
#   bash pipeline/run_local.sh --offline
#       Sem nuvem: lê ARQUIVO_MENSAGENS_LOCAL (gravado por replay_pubsub --saida),
#       grava cada tabela num .jsonl em PASTA_SAIDA_LOCAL e termina sozinho.
#       Usa as referências de exemplo (pipeline/references_example.json).
#
# Outras opções são repassadas ao main.py, com caminhos relativos à raiz do
# repositório, por exemplo:
#   bash pipeline/run_local.sh --referencias pipeline/references_example.json
source "$(dirname "$0")/../infra/common.sh"
cd "${RAIZ_REPO}"

if [[ "${1:-}" == "--offline" ]]; then
  shift
  ARGUMENTOS=(
    --entrada="${ARQUIVO_MENSAGENS_LOCAL}"
    --saida-local="${PASTA_SAIDA_LOCAL}"
    --referencias=pipeline/references_example.json
  )
else
  ARGUMENTOS=(
    --projeto="${PROJECT_ID}"
    --dataset="${DATASET}"
    --assinatura="${ASSINATURA}"
  )
fi

python3 pipeline/main.py --runner=DirectRunner "${ARGUMENTOS[@]}" "$@"
