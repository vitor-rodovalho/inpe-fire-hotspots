#!/usr/bin/env bash
# Cria o dataset do BigQuery na mesma região do bucket.
# As tabelas são criadas pelos arquivos em sql/ (veja sql/run_sql.sh).
# Uso: bash infra/05_bigquery.sh
source "$(dirname "$0")/common.sh"

DESCRICAO="Focos de calor do INPE: Bronze, Silver, Gold, referências e modelo (Trabalho 2 de PDM)"

if bq --project_id="${PROJECT_ID}" show --dataset "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1; then
  log "Dataset ${DATASET} já existe, seguindo."
else
  log "Criando dataset ${PROJECT_ID}:${DATASET} em ${REGIAO}"
  bq --project_id="${PROJECT_ID}" --location="${REGIAO}" mk \
    --dataset \
    --description="${DESCRICAO}" \
    "${PROJECT_ID}:${DATASET}"
fi

log "Pronto: dataset ${DATASET} disponível."
