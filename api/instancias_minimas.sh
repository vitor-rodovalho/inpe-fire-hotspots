#!/usr/bin/env bash
# Muda quantas instâncias da API ficam sempre ligadas, sem novo build nem deploy.
#
#   1 = dia da apresentação: sem cold start, mas cobra enquanto estiver ligada
#   0 = depois: nada fica ligado parado (padrão do deploy)
#
# Com 1, também chama /health para a instância já subir com o modelo carregado.
#
# Uso:
#   bash api/instancias_minimas.sh 1
#   bash api/instancias_minimas.sh 0
source "$(dirname "$0")/../infra/common.sh"

QTD="${1:?Informe 0 ou 1, por exemplo: bash api/instancias_minimas.sh 1}"

log "Instâncias mínimas de ${CLOUD_RUN_SERVICO}: ${QTD}"
gcloud run services update "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --min-instances="${QTD}" --quiet

URL=$(gcloud run services describe "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --format="value(status.url)")
if [[ "${QTD}" != "0" ]]; then
  log "Aquecendo ${URL}/health"
  curl -sS --fail "${URL}/health" -w "\n(%{time_total} s)\n"
else
  log "Pronto: sem instâncias ligadas paradas."
fi
