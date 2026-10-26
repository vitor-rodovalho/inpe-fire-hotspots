#!/usr/bin/env bash
# Executa um ou mais arquivos .sql no BigQuery, em ordem.
#
# Os arquivos usam marcadores que são trocados pelos valores de config.env:
#   {{PROJECT_ID}}  {{DATASET}}  {{BUCKET}}  {{DATA_CORTE}} {{PASTA_RAW_MENSAL}}  {{PASTA_MANIFESTO}}
#   {{DATASET_ORIGEM}}  O dataset de config.env, mesmo no modo teste (só sql/teste/ usa)
#
# Uso:
#   bash sql/run_sql.sh sql/bronze/01_tabela_externa_mensal.sql
#   bash sql/run_sql.sh sql/streaming/*.sql
#   SOMENTE_MOSTRAR=1 bash sql/run_sql.sh arquivo.sql   # Imprime o SQL final
#   DRY_RUN=1 bash sql/run_sql.sh arquivo.sql           # Estima bytes sem rodar
#   DATASET_TESTE=focos_teste bash sql/run_sql.sh arquivo.sql
#       Modo teste: {{DATASET}} passa a ser focos_teste, e o dataset real não é tocado
source "$(dirname "$0")/../infra/common.sh"

DATASET_ORIGEM="${DATASET}"
DATASET="${DATASET_TESTE:-${DATASET}}"

if [[ $# -eq 0 ]]; then
  echo "Uso: bash sql/run_sql.sh arquivo1.sql [arquivo2.sql ...]" >&2
  exit 1
fi

renderizar() {
  sed -e "s|{{PROJECT_ID}}|${PROJECT_ID}|g" \
      -e "s|{{DATASET}}|${DATASET}|g" \
      -e "s|{{DATASET_ORIGEM}}|${DATASET_ORIGEM}|g" \
      -e "s|{{BUCKET}}|${BUCKET}|g" \
      -e "s|{{DATA_CORTE}}|${DATA_CORTE}|g" \
      -e "s|{{PASTA_RAW_MENSAL}}|${PASTA_RAW_MENSAL}|g" \
      -e "s|{{PASTA_MANIFESTO}}|${PASTA_MANIFESTO}|g" \
      "$1"
}

for arquivo in "$@"; do
  log "Executando ${arquivo} (dataset ${DATASET})"
  if [[ "${SOMENTE_MOSTRAR:-0}" == "1" ]]; then
    renderizar "${arquivo}"
    continue
  fi
  OPCOES=(--use_legacy_sql=false --location="${REGIAO}" --project_id="${PROJECT_ID}")
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    OPCOES+=(--dry_run)
  fi
  renderizar "${arquivo}" | bq query "${OPCOES[@]}"
done
