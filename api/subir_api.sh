#!/usr/bin/env bash
# Sobe a API no Cloud Run com um comando só, do zero ou de novo.
#
# Faz, em ordem, parando no primeiro erro com a explicação do que fazer:
#   1. Confere o acesso ao projeto
#   2. Liga as APIs (não muda nada se já estiverem ligadas)
#   3. Confere a conta de serviço da API
#   4. Cria o repositório Docker, se não existir
#   5. Modelo provisório: instala as dependências, treina e envia ao bucket
#      (com --modelo v1 ou outra versão, só confere que ela já está no bucket)
#   6. Build, deploy e teste na URL pública (api/deploy.sh)
#   7. Mede a latência (api/medir_latencia.sh)
#
# Pode ser rodado de novo sem efeito colateral. Pensado para o Cloud Shell.
#
# Uso:
#   bash api/subir_api.sh                 # modelo provisório
#   bash api/subir_api.sh --modelo v1     # modelo real, já publicado no bucket
#   bash api/subir_api.sh --min 1         # dia da apresentação (sem cold start)
source "$(dirname "$0")/../infra/common.sh"
cd "${RAIZ_REPO}"

VERSAO="${MODELO_VERSAO}"
ARGS=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --modelo) VERSAO="$2"; shift 2 ;;
    --min) shift 2 ;;
    *) echo "Opção desconhecida: $1 (use --modelo V e/ou --min N)" >&2; exit 1 ;;
  esac
done
VENV="${RAIZ_REPO}/.venv-api"

erro() {
  echo >&2
  echo "ERRO: $1" >&2
  shift
  for linha in "$@"; do echo "  $linha" >&2; done
  exit 1
}

log "1/7 Acesso ao projeto ${PROJECT_ID}"
gcloud projects describe "${PROJECT_ID}" --format="value(projectId)" >/dev/null 2>&1 \
  || erro "sua conta ($(gcloud config get-value account 2>/dev/null)) não acessa ${PROJECT_ID}." \
          "Peça ao dono do projeto para incluir seu e-mail em EMAILS_EQUIPE e rodar infra/06_service_accounts.sh."

log "2/7 APIs"
bash infra/02_enable_apis.sh

log "3/7 Conta de serviço da API"
gcloud iam service-accounts describe "${SA_API_EMAIL}" >/dev/null 2>&1 \
  || erro "a conta ${SA_API_EMAIL} não existe." \
          "Peça ao dono do projeto para rodar: bash infra/06_service_accounts.sh"
echo "  ${SA_API_EMAIL} ok"

log "4/7 Repositório Docker"
bash infra/09_artifact_registry.sh

if [[ "${VERSAO}" == "provisorio" ]]; then
  log "5/7 Modelo provisório"
  if [[ ! -x "${VENV}/bin/python" ]]; then
    python3 -m venv "${VENV}"
  fi
  "${VENV}/bin/pip" install -q -r api/requirements.txt
  "${VENV}/bin/python" api/modelo_provisorio/treinar.py
  bash api/publicar_modelo.sh --versao provisorio
else
  log "5/7 Modelo ${VERSAO}"
  gcloud storage ls "gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}/manifest.json" >/dev/null 2>&1 \
    || erro "não há pacote do modelo em gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}/." \
            "Publique antes com: bash api/publicar_modelo.sh --pasta <pasta do pacote> --versao ${VERSAO}"
  echo "  Pacote gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}/ ok"
fi

log "6/7 Build e deploy"
bash api/deploy.sh "${ARGS[@]}"

URL=$(gcloud run services describe "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --format="value(status.url)")

log "7/7 Latência (o serviço já está aquecido pelo deploy; para o cold start, rode api/medir_latencia.sh depois de ~15 min parado)"
bash api/medir_latencia.sh "${URL}" 10

log "Tudo pronto: ${URL}  (documentação interativa em ${URL}/docs)"
