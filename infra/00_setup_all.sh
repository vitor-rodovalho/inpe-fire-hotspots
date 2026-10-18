#!/usr/bin/env bash
# Roda toda a configuração inicial do ambiente, na ordem certa.
# Cada etapa pode ser rodada de novo sem efeito colateral (é idempotente).
#
# Uso: bash infra/00_setup_all.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

ETAPAS=(
  01_create_project.sh
  02_enable_apis.sh
  03_budget.sh
  04_bucket.sh
  05_bigquery.sh
  06_service_accounts.sh
  07_pubsub.sh
)

for etapa in "${ETAPAS[@]}"; do
  echo "================ ${etapa} ================"
  bash "${DIR}/${etapa}"
done

echo
echo "Ambiente pronto. Próximos passos:"
echo "  1. bash infra/08_test_pubsub.sh"
echo "  2. bash sql/run_sql.sh sql/streaming/*.sql"
echo "  3. Download do INPE, Bronze e sql/reference/: veja ingestion/README.md"
