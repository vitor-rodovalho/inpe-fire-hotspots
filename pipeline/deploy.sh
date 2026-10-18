#!/usr/bin/env bash
# Sobe o pipeline no Dataflow em modo streaming.
# Recusa subir se já houver um job ativo com o mesmo nome (rode drain.sh antes).
#
# Custo aproximado: 1 worker n1-standard-2 com Streaming Engine, cerca de
# US$ 0,20 a 0,30 por hora ligado. Desligue com drain.sh entre os testes.
#
# Uso: bash pipeline/deploy.sh
source "$(dirname "$0")/../infra/common.sh"
cd "${RAIZ_REPO}/pipeline"

JOB_ATIVO=$(gcloud dataflow jobs list --region="${REGIAO}" --status=active \
  --filter="name=${DATAFLOW_JOB}" --format="value(id)")
if [[ -n "${JOB_ATIVO}" ]]; then
  echo "Já existe um job ativo chamado ${DATAFLOW_JOB} (${JOB_ATIVO})." >&2
  echo "Encerre com: bash pipeline/drain.sh" >&2
  exit 1
fi

log "Subindo ${DATAFLOW_JOB} em ${REGIAO}"
python3 main.py \
  --runner=DataflowRunner \
  --projeto="${PROJECT_ID}" \
  --dataset="${DATASET}" \
  --assinatura="${ASSINATURA}" \
  --referencias=bigquery \
  --region="${REGIAO}" \
  --job_name="${DATAFLOW_JOB}" \
  --temp_location="gs://${BUCKET}/${PASTA_DATAFLOW_TMP}" \
  --staging_location="gs://${BUCKET}/${PASTA_DATAFLOW_STAGING}" \
  --service_account_email="${SA_DATAFLOW_EMAIL}" \
  --machine_type="${DATAFLOW_MAQUINA}" \
  --num_workers=1 \
  --max_num_workers="${DATAFLOW_MAX_WORKERS}" \
  --disk_size_gb="${DATAFLOW_DISCO_GB}" \
  --enable_streaming_engine \
  --setup_file=./setup.py

log "Job enviado. Acompanhe em https://console.cloud.google.com/dataflow/jobs?project=${PROJECT_ID}"
