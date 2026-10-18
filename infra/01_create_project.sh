#!/usr/bin/env bash
# Cria o projeto GCP (se ainda não existir) e vincula a conta de faturamento.
# Uso: bash infra/01_create_project.sh
source "$(dirname "$0")/common.sh"
exigir_variavel BILLING_ACCOUNT_ID

if gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  log "Projeto ${PROJECT_ID} já existe, seguindo."
else
  log "Criando projeto ${PROJECT_ID}"
  gcloud projects create "${PROJECT_ID}" --name="${PROJECT_NAME}"
fi

gcloud config set project "${PROJECT_ID}"

log "Vinculando a conta de faturamento ${BILLING_ACCOUNT_ID}"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"

log "Pronto: projeto ${PROJECT_ID} criado e com faturamento."
