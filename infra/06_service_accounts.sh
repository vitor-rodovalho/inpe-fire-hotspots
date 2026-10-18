#!/usr/bin/env bash
# Cria as contas de serviço e dá acesso aos colegas.
#
#  - SA_DATAFLOW: usada pelos workers do Dataflow (ler Pub/Sub, gravar no
#    BigQuery, usar o bucket).
#  - SA_API: usada pelo Cloud Run (só lê o bucket, onde fica o modelo).
#  - EMAILS_EQUIPE: recebem papel de editor no projeto.
#
# Uso: bash infra/06_service_accounts.sh
source "$(dirname "$0")/common.sh"

PAPEIS_DATAFLOW_PROJETO=(
  roles/dataflow.worker
  roles/bigquery.dataEditor
  roles/bigquery.jobUser
  # O Dataflow cria uma assinatura auxiliar para acompanhar o tempo do evento
  # (timestamp_attribute), por isso precisa de editor no Pub/Sub e não só de assinate
  roles/pubsub.editor
)
PAPEL_DATAFLOW_BUCKET=roles/storage.objectAdmin
PAPEL_API_BUCKET=roles/storage.objectViewer
PAPEL_EQUIPE=roles/editor

criar_sa() {
  local nome="$1" descricao="$2"
  if gcloud iam service-accounts describe "${nome}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    log "Conta de serviço ${nome} já existe, seguindo."
  else
    log "Criando conta de serviço ${nome}"
    gcloud iam service-accounts create "${nome}" --display-name="${descricao}"
  fi
}

papel_projeto() {
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="$1" --role="$2" --condition=None --quiet >/dev/null
  echo "  ${2} -> ${1}"
}

papel_bucket() {
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="$1" --role="$2" >/dev/null
  echo "  ${2} em gs://${BUCKET} -> ${1}"
}

criar_sa "${SA_DATAFLOW}" "Workers do Dataflow (streaming de focos)"
criar_sa "${SA_API}" "API foco intenso no Cloud Run"

log "Papéis da conta do Dataflow"
for papel in "${PAPEIS_DATAFLOW_PROJETO[@]}"; do
  papel_projeto "serviceAccount:${SA_DATAFLOW_EMAIL}" "${papel}"
done
papel_bucket "serviceAccount:${SA_DATAFLOW_EMAIL}" "${PAPEL_DATAFLOW_BUCKET}"

log "Papéis da conta da API"
papel_bucket "serviceAccount:${SA_API_EMAIL}" "${PAPEL_API_BUCKET}"

if [[ -n "${EMAILS_EQUIPE:-}" ]]; then
  log "Acesso da equipe"
  for email in ${EMAILS_EQUIPE}; do
    papel_projeto "user:${email}" "${PAPEL_EQUIPE}"
  done
else
  log "EMAILS_EQUIPE vazio em config.local.env: nenhum colega recebeu acesso."
fi

log "Pronto: contas de serviço e acessos configurados."
