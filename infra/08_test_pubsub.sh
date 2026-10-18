#!/usr/bin/env bash
# Publica uma mensagem de teste no tópico e lê de volta pela assinatura.
# Rode ANTES de ligar o Dataflow: o pull confirma (ack) a mensagem, e ela
# não chega mais ao pipeline.
# Uso: bash infra/08_test_pubsub.sh
source "$(dirname "$0")/common.sh"

ID_TESTE="teste-$(date +%s)"
TS_EVENTO="2026-09-30T18:40:00Z"
MENSAGEM='{"id":"'"${ID_TESTE}"'","lat":"-9.51","lon":"-56.2","data_hora_gmt":"2026-09-30 18:40:00","satelite":"GOES-19","municipio":"ALTA FLORESTA","estado":"MATO GROSSO","pais":"Brasil","municipio_id":"5100250","estado_id":"51","pais_id":"33","numero_dias_sem_chuva":"21","precipitacao":"0","risco_fogo":"0.97","bioma":"Amazônia","frp":"35.2","publicado_em":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'

log "Publicando mensagem ${ID_TESTE} em ${TOPICO}"
gcloud pubsub topics publish "${TOPICO}" \
  --message="${MENSAGEM}" \
  --attribute="id=${ID_TESTE},ts_evento=${TS_EVENTO}"

log "Lendo de ${ASSINATURA}"
sleep 3
gcloud pubsub subscriptions pull "${ASSINATURA}" --auto-ack --limit=5
