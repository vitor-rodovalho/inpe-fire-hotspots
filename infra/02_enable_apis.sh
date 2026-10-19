#!/usr/bin/env bash
# Ativa as APIs usadas por todas as partes do projeto.
# Uso: bash infra/02_enable_apis.sh
source "$(dirname "$0")/common.sh"

APIS=(
  compute.googleapis.com              # Máquinas dos workers do Dataflow
  storage.googleapis.com
  bigquery.googleapis.com
  bigquerystorage.googleapis.com
  pubsub.googleapis.com
  dataflow.googleapis.com
  aiplatform.googleapis.com           # Vertex AI Model Registry
  run.googleapis.com                  # Cloud Run
  artifactregistry.googleapis.com     # Imagens Docker
  cloudbuild.googleapis.com           # Build da imagem
  iam.googleapis.com
  cloudresourcemanager.googleapis.com
  billingbudgets.googleapis.com       # Orçamento com alertas
)

log "Ativando ${#APIS[@]} APIs em ${PROJECT_ID} (pode levar alguns minutos)"
gcloud services enable "${APIS[@]}" --project="${PROJECT_ID}"

log "Pronto: APIs ativas."
