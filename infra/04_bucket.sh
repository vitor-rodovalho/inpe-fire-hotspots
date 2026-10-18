#!/usr/bin/env bash
# Cria o bucket do projeto e a estrutura de pastas do contrato.
# Uso: bash infra/04_bucket.sh
source "$(dirname "$0")/common.sh"

PASTAS=(
  "${PASTA_RAW_MENSAL}"
  "${PASTA_RAW_DIARIO}"
  "${PASTA_MANIFESTO}"
  "${PASTA_DATAFLOW_TMP}"
  "${PASTA_DATAFLOW_STAGING}"
  "${PASTA_MODELOS}"
)
DIAS_PARA_APAGAR_TMP=7   # Arquivos temporários do Dataflow são apagados depois disso

if gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  log "Bucket gs://${BUCKET} já existe, seguindo."
else
  log "Criando gs://${BUCKET} em ${REGIAO}"
  gcloud storage buckets create "gs://${BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGIAO}" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi

# No Cloud Storage pasta não existe de verdade: um arquivo .keep vazio faz a
# pasta aparecer no console desde o início
for pasta in "${PASTAS[@]}"; do
  printf '' | gcloud storage cp - "gs://${BUCKET}/${pasta}/.keep" >/dev/null
done

log "Regra de ciclo de vida: apagar ${PASTA_DATAFLOW_TMP} e ${PASTA_DATAFLOW_STAGING} após ${DIAS_PARA_APAGAR_TMP} dias"
REGRA=$(mktemp)
cat > "${REGRA}" <<JSON
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": ${DIAS_PARA_APAGAR_TMP},
        "matchesPrefix": ["${PASTA_DATAFLOW_TMP}/", "${PASTA_DATAFLOW_STAGING}/"]
      }
    }
  ]
}
JSON
gcloud storage buckets update "gs://${BUCKET}" --lifecycle-file="${REGRA}"
rm -f "${REGRA}"

log "Pronto: gs://${BUCKET} com as pastas do contrato."
