#!/usr/bin/env bash
# Cria o repositório Docker onde fica a imagem da API.
# Uso: bash infra/09_artifact_registry.sh
source "$(dirname "$0")/common.sh"

if gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="${REGIAO}" >/dev/null 2>&1; then
  log "Repositório ${ARTIFACT_REPO} já existe, seguindo."
else
  log "Criando repositório Docker ${ARTIFACT_REPO} em ${REGIAO}"
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker \
    --location="${REGIAO}" \
    --description="Imagens da API foco intenso"
fi

log "Pronto: ${REGIAO}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}"
