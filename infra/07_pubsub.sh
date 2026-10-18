#!/usr/bin/env bash
# Cria o tópico do replay e a assinatura que o Dataflow consome.
# Uso: bash infra/07_pubsub.sh
source "$(dirname "$0")/common.sh"

if gcloud pubsub topics describe "${TOPICO}" >/dev/null 2>&1; then
  log "Tópico ${TOPICO} já existe, seguindo."
else
  log "Criando tópico ${TOPICO}"
  gcloud pubsub topics create "${TOPICO}"
fi

if gcloud pubsub subscriptions describe "${ASSINATURA}" >/dev/null 2>&1; then
  log "Assinatura ${ASSINATURA} já existe, seguindo."
else
  log "Criando assinatura ${ASSINATURA}"
  gcloud pubsub subscriptions create "${ASSINATURA}" \
    --topic="${TOPICO}" \
    --ack-deadline="${ACK_DEADLINE_S}" \
    --message-retention-duration="${RETENCAO_MENSAGENS}" \
    --expiration-period=never
fi

log "Pronto: ${TOPICO} -> ${ASSINATURA}. Teste com: bash infra/08_test_pubsub.sh"
