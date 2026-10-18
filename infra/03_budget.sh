#!/usr/bin/env bash
# Cria um orçamento com alertas por e-mail em 50%, 90% e 100% de ORCAMENTO_USD.
#
# Atenção: orçamento só AVISA, não desliga nada. Quem desliga o gasto é o
# drain do Dataflow (pipeline/drain.sh) e o Cloud Run com 0 instâncias mínimas.
#
# O custo é medido sem descontar créditos (exclude-all-credits), para que o
# alerta dispare conforme os créditos do grupo são consumidos.
#
# Uso: bash infra/03_budget.sh
source "$(dirname "$0")/common.sh"
exigir_variavel BILLING_ACCOUNT_ID

LIMIARES_ALERTA=(0.5 0.9 1.0)

EXISTENTE=$(gcloud billing budgets list --billing-account="${BILLING_ACCOUNT_ID}" \
  --filter="displayName=${ORCAMENTO_NOME}" --format="value(name)" 2>/dev/null || true)

if [[ -n "${EXISTENTE}" ]]; then
  log "Orçamento ${ORCAMENTO_NOME} já existe (${EXISTENTE}), seguindo."
  exit 0
fi

NUMERO_PROJETO=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

REGRAS=()
for p in "${LIMIARES_ALERTA[@]}"; do
  REGRAS+=(--threshold-rule="percent=${p}")
done

log "Criando orçamento de US\$ ${ORCAMENTO_USD} para o projeto ${PROJECT_ID}"
gcloud billing budgets create \
  --billing-account="${BILLING_ACCOUNT_ID}" \
  --display-name="${ORCAMENTO_NOME}" \
  --budget-amount="${ORCAMENTO_USD}USD" \
  --filter-projects="projects/${NUMERO_PROJETO}" \
  --credit-types-treatment=exclude-all-credits \
  "${REGRAS[@]}"

log "Pronto: alertas vão para os administradores da conta de faturamento."
