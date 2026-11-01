#!/usr/bin/env bash
# Envia um pacote do modelo (manifest.json, satelites.json, o booster e assets/) para o
# bucket, na pasta que a API carrega.
#
# Uso:
#   bash api/publicar_modelo.sh                         # api/modelo_local -> MODELO_VERSAO
#   bash api/publicar_modelo.sh --pasta model/pacote --versao v1
#
# Depois de publicar uma versão nova, rode api/deploy.sh --modelo <versao> para
# a API passar a usá-la.
source "$(dirname "$0")/../infra/common.sh"

PASTA="${RAIZ_REPO}/api/modelo_local"
VERSAO="${MODELO_VERSAO}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pasta) PASTA="$2"; shift 2 ;;
    --versao) VERSAO="$2"; shift 2 ;;
    *) echo "Opção desconhecida: $1" >&2; exit 1 ;;
  esac
done

for arquivo in manifest.json satelites.json; do
  if [[ ! -f "${PASTA}/${arquivo}" ]]; then
    echo "ERRO: ${PASTA}/${arquivo} não existe." >&2
    echo "Para o modelo provisório: python api/modelo_provisorio/treinar.py" >&2
    exit 1
  fi
done

DESTINO="gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}"
log "Enviando ${PASTA} para ${DESTINO}"
gcloud storage cp -r "${PASTA}"/* "${DESTINO}/"
gcloud storage ls -r "${DESTINO}/"

log "Pronto. Para a API usar: bash api/deploy.sh --modelo ${VERSAO}"
