#!/usr/bin/env bash
# Encerra o job do Dataflow sem perder dados: para de ler o Pub/Sub, termina o
# que já estava em andamento (inclusive as janelas abertas) e desliga os workers.
#
# Uso:
#   bash pipeline/drain.sh             # Drain (recomendado)
#   bash pipeline/drain.sh --cancelar  # Para na hora, descartando o que estava em andamento
source "$(dirname "$0")/../infra/common.sh"

JOB_ATIVO=$(gcloud dataflow jobs list --region="${REGIAO}" --status=active \
  --filter="name=${DATAFLOW_JOB}" --format="value(id)")
if [[ -z "${JOB_ATIVO}" ]]; then
  log "Nenhum job ativo chamado ${DATAFLOW_JOB}."
  exit 0
fi

if [[ "${1:-}" == "--cancelar" ]]; then
  log "Cancelando ${JOB_ATIVO}"
  gcloud dataflow jobs cancel "${JOB_ATIVO}" --region="${REGIAO}"
else
  log "Drenando ${JOB_ATIVO} (leva alguns minutos para os workers desligarem)"
  gcloud dataflow jobs drain "${JOB_ATIVO}" --region="${REGIAO}"
fi
