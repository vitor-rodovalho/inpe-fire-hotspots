#!/usr/bin/env bash
# Mede o tempo de resposta de /predict, para os slides.
#
# A primeira chamada depois de o serviço ficar parado (cerca de 15 minutos sem
# requisições, com 0 instâncias mínimas) inclui o cold start: subir o contêiner
# e baixar o modelo. As seguintes mostram a latência normal.
#
# Uso:
#   bash api/medir_latencia.sh                          # URL do Cloud Run, 20 chamadas
#   bash api/medir_latencia.sh http://localhost:8080 50
source "$(dirname "$0")/../infra/common.sh"

URL="${1:-$(gcloud run services describe "${CLOUD_RUN_SERVICO}" --region="${REGIAO}" --format="value(status.url)")}"
QTD="${2:-20}"
CORPO="${RAIZ_REPO}/api/exemplos/foco.json"
TEMPOS=$(mktemp)

log "${QTD} chamadas a ${URL}/predict"
for i in $(seq 1 "${QTD}"); do
  curl -sS -o /dev/null --fail -X POST "${URL}/predict" \
    -H "Content-Type: application/json" --data-binary @"${CORPO}" \
    -w "%{time_total}\n" >> "${TEMPOS}"
done

# Tempos em ms: a primeira chamada à parte (pode ter cold start), depois mediana e p95 das demais
awk '{ printf "%.0f\n", $1 * 1000 }' "${TEMPOS}" > "${TEMPOS}.ms"
echo "Primeira chamada: $(head -1 "${TEMPOS}.ms") ms"
tail -n +2 "${TEMPOS}.ms" | sort -n | awk '
  { v[NR] = $1 }
  END {
    if (NR == 0) exit
    p50 = v[int((NR + 1) / 2)]; p95 = v[int(NR * 0.95 + 0.5) > 0 ? int(NR * 0.95 + 0.5) : 1]
    printf "Demais %d chamadas: mediana %d ms, p95 %d ms, máximo %d ms\n", NR, p50, p95, v[NR]
  }'
rm -f "${TEMPOS}" "${TEMPOS}.ms"
