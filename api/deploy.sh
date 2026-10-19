#!/usr/bin/env bash
# Constrói a imagem da API no Cloud Build, guarda no Artifact Registry e
# publica o serviço no Cloud Run. No fim, chama /health e /predict na URL
# pública para confirmar que está respondendo.
#
# Custo: o Cloud Run cobra por requisição. Com --min 0 (padrão), nada fica
# ligado parado. No dia da apresentação, --min 1 evita o cold start; depois,
# volte para 0.
#
# Uso:
#   bash api/deploy.sh                    # modelo MODELO_VERSAO, 0 instâncias mínimas
#   bash api/deploy.sh --modelo v1        # outra versão do pacote no bucket
#   bash api/deploy.sh --min 1            # dia da apresentação
#
# Pré-requisitos: infra/00_setup_all.sh (APIs, bucket, conta da API e
# repositório Docker) e o pacote do modelo no bucket (api/publicar_modelo.sh).
source "$(dirname "$0")/../infra/common.sh"
cd "${RAIZ_REPO}/api"

VERSAO="${MODELO_VERSAO}"
MIN_INSTANCIAS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --modelo) VERSAO="$2"; shift 2 ;;
    --min) MIN_INSTANCIAS="$2"; shift 2 ;;
    *) echo "Opção desconhecida: $1" >&2; exit 1 ;;
  esac
done

MODELO_URI="gs://${BUCKET}/${PASTA_MODELOS}/${VERSAO}"
# A tag é o commit, para saber exatamente qual código está no ar
TAG="$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . || echo '-alterado')"
IMAGEM="${REGIAO}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${CLOUD_RUN_SERVICO}:${TAG}"

if ! gcloud storage ls "${MODELO_URI}/manifest.json" >/dev/null 2>&1; then
  echo "ERRO: não há pacote do modelo em ${MODELO_URI}." >&2
  echo "Publique antes com: bash api/publicar_modelo.sh --versao ${VERSAO}" >&2
  exit 1
fi

log "Construindo ${IMAGEM}"
if ! gcloud builds submit . --tag="${IMAGEM}"; then
  NUMERO=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
  echo >&2
  echo "ERRO no build. Se a mensagem fala em permissão (storage, artifactregistry), a conta" >&2
  echo "do Cloud Build não pode gravar a imagem. O dono do projeto roda:" >&2
  echo "  gcloud projects add-iam-policy-binding ${PROJECT_ID} \\" >&2
  echo "    --member=serviceAccount:${NUMERO}-compute@developer.gserviceaccount.com \\" >&2
  echo "    --role=roles/cloudbuild.builds.builder" >&2
  exit 1
fi

log "Publicando ${CLOUD_RUN_SERVICO} em ${REGIAO} (modelo ${VERSAO}, mínimo ${MIN_INSTANCIAS} instância)"
gcloud run deploy "${CLOUD_RUN_SERVICO}" \
  --image="${IMAGEM}" \
  --region="${REGIAO}" \
  --service-account="${SA_API_EMAIL}" \
  --allow-unauthenticated \
  --set-env-vars="MODELO_URI=${MODELO_URI}" \
  --memory="${CLOUD_RUN_MEMORIA}" \
  --cpu=1 \
  --cpu-boost \
  --min-instances="${MIN_INSTANCIAS}" \
  --max-instances="${CLOUD_RUN_MAX_INSTANCIAS}" \
  --concurrency=40 \
  --timeout=30 \
  --labels="frente=d,modelo=${VERSAO//[^a-z0-9_-]/_}"

URL=$(gcloud run services describe "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --format="value(status.url)")

log "Conferindo ${URL}"
if [[ "$(curl -s -o /dev/null -w "%{http_code}" "${URL}/health")" == "403" ]]; then
  echo "ERRO: o serviço está no ar, mas não é público (403). O papel de editor não pode" >&2
  echo "liberar acesso público. O dono do projeto roda:" >&2
  echo "  gcloud run services add-iam-policy-binding ${CLOUD_RUN_SERVICO} --region=${REGIAO} \\" >&2
  echo "    --member=allUsers --role=roles/run.invoker" >&2
  exit 1
fi
curl -sS --fail "${URL}/health"
echo
curl -sS --fail -X POST "${URL}/predict" \
  -H "Content-Type: application/json" \
  --data-binary @exemplos/foco.json \
  -w "\n(tempo total da chamada: %{time_total} s)\n"

log "Pronto: ${URL}  (documentação em ${URL}/docs)"
