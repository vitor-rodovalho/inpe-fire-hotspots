# Resultados do modelo

Gerado por `model/resultados.py` em 2026-11-02 07:54 UTC. É o material do slide de resultados: o modelo contra os baselines, o que ele usa para decidir, como se comporta nos focos que chegam pelo streaming e o que precisa ser dito como limitação. As métricas da avaliação estão em detalhe em [model_metrics.md](model_metrics.md).

## O modelo

Um classificador *boosted tree* do BigQuery ML (`focos.modelo_foco_intenso`, registrado no Vertex AI como `v1`) que estima a probabilidade de um foco de calor ser **intenso**, isto é, de ter FRP acima do percentil 90 da sua órbita (202,1 MW nos geoestacionários e 28,4 MW nos polares). Usa só o que se sabe no momento da detecção: posição, hora, mês, tipo de órbita, bioma e clima.

- **Treino:** 2.530.560 focos de out/2025 a ago/2026 (10,0% intensos).
- **Teste:** 756.172 focos de set/2026 (10,8% intensos). A divisão é por tempo, e não por sorteio, porque focos vizinhos são quase cópias.

## 1. Modelo contra os baselines (mês de teste)

| Modelo | ROC AUC | Precisão | Recall | Acurácia |
|---|---|---|---|---|
| **Modelo (boosted tree do BigQuery ML)** | 0,725 | 0,183 | 0,649 | 0,650 |
| Baseline B: regressão logística só com órbita e hora | 0,649 | 0,138 | 0,894 | 0,389 |
| Baseline A: sempre "não intenso" | 0,500 | - | 0,000 | 0,892 |

O critério do plano é ROC AUC de pelo menos 0,70 e ganhar claramente da regressão logística: o modelo tem 0,725, 0,076 acima dela. O ROC AUC é a chance de o modelo dar nota maior a um foco intenso do que a um não intenso (0,5 é o acaso). A acurácia não serve de critério: responder sempre "não intenso" acerta 89,2%.

## 2. O que o modelo usa para decidir

Participação de cada variável no ganho do modelo (`ML.FEATURE_IMPORTANCE`):

| Variável | Participação no ganho | Vezes usada nas árvores |
|---|---|---|
| `hora` | 40,0% | 4.220 |
| `tipo_orbita` | 20,7% | 859 |
| `lon` | 7,5% | 8.312 |
| `lat` | 6,8% | 7.683 |
| `bioma` | 6,7% | 919 |
| `mes` | 6,7% | 3.001 |
| `risco_fogo` | 4,6% | 3.746 |
| `numero_dias_sem_chuva` | 4,5% | 4.646 |
| `precipitacao` | 2,5% | 2.826 |

- **`hora` e `tipo_orbita` somam 61% do ganho.** O fogo é mais forte à tarde, mas a hora também indica qual satélite passou (os polares cruzam em horários fixos), e sensores diferentes medem energias diferentes. Parte do que o modelo aprende é "qual instrumento mediu".
- **Onde o foco está** (`lat`, `lon` e `bioma`) soma 21%.
- **O clima no ponto** (risco de fogo, dias sem chuva e precipitação) soma 12%: ajuda, mas pesa menos do que se esperaria.

## 3. O modelo em produção (streaming)

Os focos que chegam pelo streaming (outubro de 2026) são pontuados pela `vw_previsoes`. Nos que têm FRP, a previsão é comparada com o real, com o mesmo limiar de decisão de 0,5 do teste:

| Período | Focos | Acurácia | Precisão | Recall |
|---|---|---|---|---|
| mês de teste (set/2026) | 756.172 | 0,650 | 0,183 | 0,649 |
| streaming, todas as horas | 613.145 | 0,666 | 0,185 | 0,673 |
| streaming, última hora (01/11 00:00 UTC) | 456 | 0,603 | 0,175 | 0,516 |

**O modelo se mantém fora do período de treino:** em outubro, a precisão foi de 0,185 e o recall de 0,673, contra 0,183 e 0,649 em setembro. Com a demo ao vivo, a linha da última hora muda à medida que os focos chegam.

## 4. Estimativas para os focos sem FRP

Em outubro, 23.672 focos chegaram sem FRP. Para eles, a previsão é a única informação de intensidade, e fica separada do que foi medido (`uso = 'estimativa'`):

| Satélite | Órbita | Focos | Probabilidade média | Marcados como intensos |
|---|---|---|---|---|
| METOP-B | polar | 10.932 | 0,647 | 89% |
| METOP-C | polar | 9.937 | 0,644 | 91% |
| MSG-03 | geoestacionario | 2.803 | 0,426 | 39% |

Na órbita polar, os satélites sem FRP recebem probabilidade média de 0,65: eles nunca aparecem no treino, porque sem FRP não há rótulo, e o modelo os trata como qualquer foco da órbita polar, com as mesmas variáveis. É uma extrapolação, e deve ser apresentada assim.

## 5. Limitações (para dizer no slide)

- **O limiar de "intenso" é nosso.** O INPE não tem escala oficial, e o FRP de um foco isolado é impreciso: o resultado é uma triagem, não uma medida.
- **Na órbita polar, "intenso" depende em parte do sensor.** Com um limiar único por órbita, a parcela de intensos vai de 38% (AQUA) a 0,8% (NPP-375D).
- **A probabilidade não é calibrada.** O treino dá mais peso à classe rara, e com o limiar de 0,5 o modelo marca intensos demais: a acurácia (0,650) fica abaixo da de quem sempre diz "não" (0,892). Para ordenar os focos (triagem), o que vale é o ROC AUC.
- **As estimativas dos satélites sem FRP são extrapolação** (seção 4).

## Como reproduzir

```bash
set -a; source config.env; set +a
python3 model/treino_avaliacao.py         # treino e avaliação (docs/model_metrics.md)
python3 model/previsoes_monitoramento.py  # views de previsões e monitoramento
python3 model/resultados.py               # este documento
```
