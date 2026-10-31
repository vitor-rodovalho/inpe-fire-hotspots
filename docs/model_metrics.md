# Métricas do modelo (C4)

Gerado por `model/treino_avaliacao.py` em 2026-10-31 22:36 UTC, a partir dos SQL de `sql/modelo/`. O modelo é o boosted tree do BigQuery ML do plano (`focos.modelo_foco_intenso`), treinado nos focos de treino da `gold_treino` (out/2025 a ago/2026) e avaliado no mês de teste (set/2026), com os dois baselines nos mesmos focos.

## Resultado no mês de teste

| Modelo | ROC AUC | ROC AUC do `ML.EVALUATE` | Precisão | Recall | Acurácia | F1 |
|---|---|---|---|---|---|---|
| Modelo (boosted tree) | 0,725 | 0,725 | 0,183 | 0,649 | 0,650 | 0,285 |
| Baseline B: regressão logística (`tipo_orbita`, `hora`) | 0,649 | 0,595 | 0,138 | 0,894 | 0,389 | 0,240 |
| Baseline A: sempre a classe majoritária | 0,500 | 0,500 | - | 0,000 | 0,892 | - |

A coluna ROC AUC traz o valor exato, calculado a partir do `ML.PREDICT` em `sql/modelo/03_avaliacao.sql`. O do `ML.EVALUATE` é aproximado e erra quando muitos focos recebem a mesma probabilidade: é o caso da regressão logística, que só tem 47 valores distintos. No boosted tree, os dois coincidem.

**Critério do plano:** ROC AUC de pelo menos 0,70 e ganhar claramente da regressão logística. O modelo tem 0,725, 0,076 acima dela: passou. Para comparar, o XGBoost local da C2, com a mesma Gold, teve 0,725.

Precisão, recall, acurácia e F1 usam o limiar de decisão de 0,5. Com `auto_class_weights`, a probabilidade não é calibrada e esse limiar marca mais intensos do que existem: a acurácia fica abaixo da do baseline A, que acerta os não intensos sem aprender nada. Por isso o critério é o ROC AUC.

## Curva ROC (`ML.ROC_CURVE`)

Precisão e recall dos intensos em alguns limiares de decisão:

| Limiar | Precisão | Recall | Taxa de falsos positivos |
|---|---|---|---|
| 0,30 | 0,145 | 0,927 | 0,661 |
| 0,40 | 0,157 | 0,844 | 0,548 |
| 0,50 | 0,183 | 0,646 | 0,348 |
| 0,60 | 0,247 | 0,388 | 0,143 |
| 0,70 | 0,329 | 0,214 | 0,053 |
| 0,80 | 0,398 | 0,110 | 0,020 |

## Treino e registro

- **Modelo:** `focos.modelo_foco_intenso`, criado em 31/10/2026 22:26 UTC, 300 iterações (10 minutos de treino informados pelo modelo), com as opções do plano e os hiperparâmetros da C2 (`NO_SPLIT`, profundidade 6, taxa de aprendizado 0,1, subamostragem de 0,8 nas linhas e nas colunas).
- **Vertex AI Model Registry:** `modelo_foco_intenso` versão 1 (v1, default).
- **Job de `01_modelo_foco_intenso.sql`:** 12 minutos, 31,6 GiB faturados (US$ 0,19).
- **Job de `02_baseline_logistica.sql`:** 5 minutos, 0,1 GiB faturados (US$ 0,02).
- **Custo dos treinos:** US$ 0,21, dentro de 1 TiB grátis por mês.
