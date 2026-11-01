#!/usr/bin/env bash
# Sobe a API no Cloud Run com um comando só, do zero ou de novo.
#
# Faz, em ordem, parando no primeiro erro com a explicação do que fazer:
#   1. Confere o acesso ao projeto
#   2. Liga as APIs (não muda nada se já estiverem ligadas)
#   3. Confere a conta de serviço da API
#   4. Cria o repositório Docker, se não existir
#   5. Pacote do modelo:
#      - v1 (padrão): se ainda não estiver no bucket, roda api/montar_pacote_v1.py
#        (EXPORT MODEL, 50 focos de paridade e conferência; centavos)
#      - provisorio: treina o modelo de teste e envia ao bucket
#   6. Token da API (reaproveita o do serviço ou gera um) e build, deploy e
#      teste na URL pública (api/deploy.sh)
#   7. Testa a API no ar: paridade, erros 422 e latência (api/testar_api.py),
#      gravando docs/api_evidence.md
#
# Pode ser rodado de novo sem efeito colateral. Pensado para o Cloud Shell.
#
# Uso:
#   bash api/subir_api.sh                        # modelo real (MODELO_VERSAO de config.env)
#   bash api/subir_api.sh --modelo provisorio    # modelo de teste
#   bash api/subir_api.sh --min 1                # dia da apresentação (sem cold start)
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
PACOTE="gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}"

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

log "5/7 Pacote do modelo ${VERSAO}"
[[ -x "${VENV}/bin/python" ]] || python3 -m venv "${VENV}"
if [[ "${VERSAO}" == "provisorio" ]]; then
  "${VENV}/bin/pip" install -q -r api/requirements.txt
  "${VENV}/bin/python" api/modelo_provisorio/treinar.py
  bash api/publicar_modelo.sh --versao provisorio
elif [[ "${VERSAO}" == "v1" ]]; then
  if gcloud storage ls "${PACOTE}/manifest.json" >/dev/null 2>&1 && [[ -f model/paridade.jsonl ]]; then
    echo "  ${PACOTE}/ já está pronto e model/paridade.jsonl existe, seguindo."
  else
    "${VENV}/bin/pip" install -q -r api/requirements-pacote.txt
    (cd api && "${VENV}/bin/python" montar_pacote_v1.py)
  fi
else
  gcloud storage ls "${PACOTE}/manifest.json" >/dev/null 2>&1 \
    || erro "não há pacote do modelo em ${PACOTE}/." \
            "Publique antes com: bash api/publicar_modelo.sh --pasta <pasta do pacote> --versao ${VERSAO}"
  echo "  ${PACOTE}/ ok"
fi

log "6/7 Build e deploy"
# Token fixo de POST /predict, guardado em config.local.env (fora do Git). Se o
# serviço já tiver um, ele é reaproveitado, para não invalidar o de quem já usa
if [[ -z "${API_TOKEN:-}" ]]; then
  API_TOKEN=$(cd api && python3 -c "from cliente_api import ler_token; print(ler_token())")
  if [[ -n "${API_TOKEN}" ]]; then
    echo "  Token da API reaproveitado do serviço no Cloud Run"
  else
    API_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "  Token da API gerado"
  fi
  [[ -f config.local.env ]] || cp config.local.env.example config.local.env
  if grep -q "^API_TOKEN=" config.local.env; then
    sed -i "s/^API_TOKEN=.*/API_TOKEN=${API_TOKEN}/" config.local.env
  else
    printf '\nAPI_TOKEN=%s\n' "${API_TOKEN}" >> config.local.env
  fi
  export API_TOKEN
  echo "  Guardado em config.local.env (fora do Git). Para ver: grep API_TOKEN config.local.env"
fi

bash api/deploy.sh --modelo "${VERSAO}" "${ARGS[@]}"

URL=$(gcloud run services describe "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --format="value(status.url)")

log "7/7 Teste da API no ar"
if [[ "${VERSAO}" == "provisorio" ]]; then
  # A paridade é com o modelo real; com o provisório, só a latência
  bash api/medir_latencia.sh "${URL}" 10
else
  python3 api/testar_api.py "${URL}" --gravar
fi

log "Tudo pronto: ${URL}  (documentação interativa em ${URL}/docs)"
