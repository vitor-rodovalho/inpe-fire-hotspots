# model/

Frente C: exploração, limiar de "foco intenso", modelo e exportação. O modelo
do projeto é o boosted tree do BigQuery ML, como o plano define (ver "Custos no
GCP e a escolha do BigQuery ML", no fim).

## C1. Exploração e limiar

`exploracao_limiar.py` lê da Silver histórica (`focos.silver_focos_historico`,
A5) os meses de treino (out/2025 a ago/2026), com o FRP já limpo (vazio e -999
como nulo), e mostra, por tipo de órbita e por satélite:

1. a parcela de focos sem FRP, ao lado da do resumo de A1
   (`docs/data_profile.md`, 1,7% nos 12 meses);
2. a distribuição do FRP (percentis 50, 75, 90, 95 e 99 e o máximo);
3. o limiar proposto por tipo de órbita e quantos focos de cada satélite ele
   marcaria como intensos.

O tipo de órbita vem de `focos.satelites`, a mesma tabela usada pelo pipeline e
pela API. Nada é gravado sem `--gravar`; com ele, o script substitui
`focos.limiar_frp` no esquema do contrato (`tipo_orbita, limiar, percentil,
calculado_em`).

```bash
pip install -r model/requirements.txt
set -a; source config.env; set +a
python3 model/exploracao_limiar.py                  # exploração, sem gravar
python3 model/exploracao_limiar.py --percentil 95   # compara outro limiar
python3 model/exploracao_limiar.py --gravar         # grava o P90 em focos.limiar_frp
```

Depois de gravar, avise quem consome a tabela: a Frente A, que usa o limiar no
rótulo da Gold de treino (A7), e a Frente B, que precisa drenar e subir de novo
o Dataflow, porque ele lê o limiar só ao iniciar (B4).

### Por que o percentil 90

O INPE não tem escala oficial de intensidade, e a FAQ avisa que o FRP de um
foco isolado é impreciso, então o limiar é uma escolha nossa e o resultado deve
ser lido como triagem. O percentil 90 marca como intensos os 10% de focos com
maior FRP: uma classe minoritária, com exemplos suficientes para o modelo
aprender, que separa as frentes de fogo fortes da massa de focos pequenos. O
cálculo é por tipo de órbita, porque sensores diferentes medem energias
diferentes por pixel, e usa só os meses de treino, para que o mês de teste
(set/2026) não influencie a regra que define o rótulo.

### Valores gravados

| tipo_orbita | limiar (MW) | percentil |
|---|---|---|
| geoestacionario | 202,1 | 90 |
| polar | 28,4 | 90 |

Os valores batem com os candidatos do notebook 01 (202,2 e 28,4 MW), que usou
`APPROX_QUANTILES`; a diferença de 0,1 MW vem do cálculo exato no pandas. O
valor exato com todas as casas está em `focos.limiar_frp`.

O limiar foi gravado em 20/10 a partir da Bronze, com as mesmas regras de
limpeza, antes de a Silver histórica existir. A Silver tem os mesmos 3.342.337
focos da Bronze, sem descartes, então ler dela dá os mesmos valores: rode o
script sem `--gravar` para conferir, e só grave de novo se algo mudar (a Gold de
treino e o Dataflow dependem dessa tabela).

### Observações da exploração

Meses de treino (out/2025 a ago/2026), focos com FRP:

- **Focos sem FRP:** 0,8% nos geoestacionários e 1,5% nos polares. Só METOP-B,
  METOP-C e MSG-03 (100% sem FRP) não trazem o campo; os demais satélites
  trazem em todos os focos. O limiar do geoestacionário vem só do GOES-19.
- **O limiar por órbita não é uniforme dentro da órbita polar.** Os sensores
  MODIS (AQUA e TERRA, 1 km) medem FRP maior por pixel que os VIIRS (NOAA e
  NPP, 375 m): o P90 do AQUA_M-T é 92,1 MW e o do NPP-375D é 5,4 MW. Com o
  limiar único de 28,4 MW, a parcela de focos intensos por satélite fica em
  38,3% (AQUA_M-T), 31,7% (TERRA_M-T), 21,6% (TERRA_M-M), 20,4% (AQUA_M-M),
  10,0% (NPP-375), 8,5% (NOAA-21), 7,2% (NOAA-20) e 0,8% (NPP-375D).
- **Decisão:** manter o limiar por tipo de órbita, como o plano e o contrato
  definem. A Gold de treino (A7), o Dataflow (B4), as views e a API juntam o
  limiar por `tipo_orbita`, e o modelo também não recebe o satélite como
  variável, só a órbita. Um limiar por satélite exigiria mudar o contrato e as
  Frentes A, B e D.
- **Limitação para os slides:** na órbita polar, o rótulo "intenso" depende em
  parte do sensor, não só da intensidade do fogo. O resultado deve ser lido
  como triagem.

<!-- C2: início (gerado por model/sinal_modelo.py) -->
## C2. Sinal do modelo

Gerado por `model/sinal_modelo.py` em 2026-10-27 03:56 UTC. XGBoost local sobre a Gold de treino (`focos.gold_treino`): treino de out/2025 a ago/2026 e teste em set/2026, só focos com FRP, rótulo pelo limiar de `focos.limiar_frp`, categóricas em one-hot (xgboost 2.1.3). É o teste de sinal do plano, antes do modelo do BigQuery ML.

- Treino: 2.530.560 focos, 10.0% intensos.
- Teste: 756.172 focos, 10.8% intensos.

| Modelo (mês de teste) | ROC AUC | PR AUC |
|---|---|---|
| XGBoost, variáveis do plano | 0.725 | 0.251 |
| XGBoost sem `mes` | 0.722 | 0.248 |
| Baseline B: regressão logística (`tipo_orbita`, `hora`) | 0.649 | 0.171 |
| Baseline A: sempre a classe majoritária | 0.500 | 0.108 |

O baseline A tem acurácia de 89.2% sem aprender nada, e por isso a comparação usa ROC AUC. A PR AUC mostra o ganho na classe rara (a de um classificador sem sinal é a própria parcela de intensos).

Variáveis mais importantes do XGBoost (ganho): `hora` (1,390), `tipo_orbita=polar` (801), `bioma=Mata Atlântica` (626), `tipo_orbita=geoestacionario` (493), `lon` (260), `mes` (221), `lat` (211), `bioma=Cerrado` (206).

### Decisão

**Seguir com as variáveis do plano.** O XGBoost passa do alvo de 0.70 de ROC AUC e ganha da regressão logística por 0.077.

Sem `mes`, o ROC AUC muda em -0.003. Set/2026 não aparece no treino, então no teste o mês é sempre um valor que o modelo nunca viu.
<!-- C2: fim -->

<!-- C3: início (gerado por model/exportacao_brinquedo.py) -->
## C3. Exportação de brinquedo

Gerado por `model/exportacao_brinquedo.py` em 2026-10-31 22:02 UTC. O boosted tree do BigQuery ML foi treinado com 496 focos de treino da Gold (32 intensos), com as opções do plano e os hiperparâmetros da C2 (300 iterações), exportado com `EXPORT MODEL` e carregado em Python. O treino levou 9 minutos e faturou 24.8 GiB (US$ 0.15).

### Resultado

- **Versão do XGBoost:** o BigQuery ML exporta o Booster no formato do XGBoost 0.82 (documentação do `EXPORT MODEL`), sem fixar versão no `predictor.py`. A API fixa `xgboost-cpu==2.1.3`, e o Booster carrega no xgboost 2.1.3 (300 árvores, 9 colunas, objetivo `multi:softprob`), sem precisar de imagem antiga. A carga avisa "Loading model from XGBoost < 1.0.0, consider saving it again": na C5, o pacote v1 leva também o Booster salvo de novo em JSON, para não depender desse formato.
- **Arquivos do export:** `assets/4_categorical_label.txt`, `assets/5_categorical_label.txt`, `assets/model_metadata.json`, `explanation_metadata.json`, `main.py`, `model.bst`, `xgboost_predictor-0.1.tar.gz`.
- **Paridade:** 450 de 450 probabilidades do Booster iguais às do `ML.PREDICT` (maior diferença 2.7e-10). Por grupo: sem nulos: 400 de 400; bioma nulo: 0 de 0; clima nulo: 50 de 50. Passou.
- **Bioma nulo:** a amostra não teve focos sem bioma (o mês de teste não tem nenhum), então a regra do `_null_filler` vem do `predictor.py` do export. A versão atual do script troca o bioma de focos de teste por `NULL` para conferir; com o modelo real, isso entra na C5.

### Passo a passo da preparação das variáveis (para a Frente D)

É o que o `ML.PREDICT` faz e o que a API precisa reproduzir para dar a mesma probabilidade:

1. `hora` = `EXTRACT(HOUR FROM data_hora_gmt)` e `mes` = `EXTRACT(MONTH FROM data_hora_gmt)`, em UTC, como na Gold.
2. `tipo_orbita` vem de `focos.satelites`.
3. O vetor tem as variáveis na ordem de `feature_names` em `assets/model_metadata.json`, uma coluna por variável (as categóricas não viram one-hot):

   0. `lat`: o valor; nulo vira -9.600124012096773
   1. `lon`: o valor; nulo vira -48.97768381048386
   2. `hora`: o valor; nulo vira 13.02620967741935
   3. `mes`: o valor; nulo vira 8.754032258064521
   4. `tipo_orbita`: índice no vocabulário (0 = `_null_filler`, 1 = `geoestacionario`, 2 = `polar`)
   5. `bioma`: índice no vocabulário (0 = `_null_filler`, 1 = `Amazônia`, 2 = `Caatinga`, 3 = `Cerrado`, 4 = `Mata Atlântica`, 5 = `Pampa`, 6 = `Pantanal`)
   6. `numero_dias_sem_chuva`: o valor; nulo vira 15.26004228329808
   7. `precipitacao`: o valor; nulo vira 0.4691786447638608
   8. `risco_fogo`: o valor; nulo vira 0.7876288659793814

4. Carregar com `xgb.Booster(model_file="model.bst")` e chamar `predict` sem valores ausentes. A saída tem uma coluna por classe, na ordem de `class_names` (['true', 'false']): a probabilidade de intenso é a coluna de `"true"`.

O `predictor.py` que vem no export (`xgboost_predictor-0.1.tar.gz`) não serve à API como está: ele quebra com numérica nula (`float(None)`), enquanto o BigQuery ML usa a média, e deixa a categoria nula como ausente, enquanto o vocabulário do export reserva o índice 0 (`_null_filler`) para ela.

### Para a Frente D

- O modelo real (C4) é exportado igual, em `gs://<BUCKET>/modelos/foco_intenso/v1/` (C5), com os mesmos arquivos. O `modelo.py` da API, que hoje monta one-hot pelo `manifest.json` do modelo provisório, precisa montar o vetor como acima, lendo os vocabulários e as médias do próprio export.
- O limiar de decisão de `intenso` sai da C4. Com `auto_class_weights`, a probabilidade não é calibrada, e 0,5 marca intensos demais.
<!-- C3: fim -->

## C4. Treino e avaliação

O modelo do projeto é o boosted tree do BigQuery ML do plano, em
`sql/modelo/` (rodam com `sql/run_sql.sh` ou com o script abaixo):

| Arquivo | O que faz |
|---|---|
| `01_modelo_foco_intenso.sql` | `CREATE MODEL` do plano, com registro no Vertex AI (`modelo_foco_intenso`, alias `v1`) e os hiperparâmetros da C2 |
| `02_baseline_logistica.sql` | Baseline B: regressão logística com `tipo_orbita` e `hora` |
| `03_avaliacao.sql` | `ML.EVALUATE` do modelo e dos baselines em set/2026, com o ROC AUC exato |
| `04_roc_curve.sql` | `ML.ROC_CURVE` do modelo em set/2026 |

```bash
set -a; source config.env; set +a
python3 model/treino_avaliacao.py --so-estimar   # dry run dos treinos, sem custo
python3 model/treino_avaliacao.py                # treina, avalia e grava docs/model_metrics.md
```

Resultado em 31/10 (detalhes em `docs/model_metrics.md`): ROC AUC de 0,725 no
mês de teste, contra 0,649 da regressão logística e 0,500 da classe
majoritária, o mesmo valor do XGBoost local da C2. O treino levou 12 minutos e
custou US$ 0,19.

Os hiperparâmetros são os da C2, porque o plano não fixa nenhum: 300
iterações, profundidade 6, taxa de aprendizado 0,1 e subamostragem de 0,8, com
o treino em todos os meses (`NO_SPLIT`). O padrão do BigQuery ML sortearia
focos do treino para a parada antecipada, e focos vizinhos no tempo e no
espaço são quase cópias, então esse sorteio mediria mal.

## Custos no GCP e a escolha do BigQuery ML

Regra da Frente C: nada roda no GCP sem antes estimar o que vai ser
processado e quanto vai custar.

- **Antes de rodar:** dry-run (`DRY_RUN=1 bash sql/run_sql.sh arquivo.sql`, ou
  `dry_run=True` na API). Os scripts de `model/` já fazem isso e param se a
  consulta passar do limite (`LIMITE_GB_CONSULTA`, com `maximum_bytes_billed`).
- **Tarifas:** consulta no BigQuery, US$ 6,25 por TiB lido (1 TiB grátis por
  mês). No BigQuery ML, a tarifa de US$ 312,50 por TiB vale só para os modelos
  internos (regressões linear e logística, k-means, PCA, ARIMA). O boosted
  tree é um modelo externo: o treino roda no Vertex AI e é cobrado a US$ 6,25
  por TiB, somando o pré-processamento e o tempo de máquina convertido em bytes.
  `ML.EVALUATE` e `ML.PREDICT` também custam US$ 6,25 por TiB e entram na cota
  grátis.
- **Depois de rodar:** conferir `totalBytesBilled` do job e, no dia seguinte, o
  relatório de faturamento por SKU.

### O job de 20/10 e o teste de viabilidade

O primeiro boosted tree de teste, em 20/10, com 500 focos, foi cancelado depois
de 21 minutos, com 43,8 GiB faturados. Na época, esses bytes foram lidos na
tarifa de US$ 312,50 por TiB (US$ 10 a 14), e o modelo passou a ser um XGBoost
local, a reserva do plano. Na tarifa certa, o job custou US$ 0,27 e entrou na
cota grátis: são os 0,05 TiB da SKU "Analysis" no relatório de 27/10.

Para decidir com jobs que terminam, um teste de viabilidade mediu, de 29 a
31/10, com os hiperparâmetros da C2:

| Etapa | O que mediu | Resultado |
|---|---|---|
| E0 | O job de 20/10 (500 focos, 10 iterações), em `INFORMATION_SCHEMA` | 1.257 s, 43,8 GiB, US$ 0,27 |
| E1 | Treino com 9.808 focos (300 iterações) | 19 min, 53,7 GiB, US$ 0,33; registro no Vertex AI ok |
| E2 | Treino com 253.549 focos | 19 min, 53,2 GiB, US$ 0,32 |
| E3 | ROC AUC em set/2026, contra o XGBoost local na mesma amostra | 0,670 x 0,665 (10 mil); 0,714 x 0,716 (250 mil) |

Os jobs levaram de 9 a 21 minutos e custaram de US$ 0,15 a 0,33, com 500 a
250 mil focos e 10 a 300 iterações, sem relação clara com nenhum dos dois: o
tempo é quase todo de subir as máquinas no Vertex AI (o de 31/10, da C3, com
496 focos, levou 9 minutos e custou US$ 0,15). A projeção para a Gold inteira
(2,5 milhões) é de US$ 0,30 a 1,00. O teste todo
custou cerca de US$ 0,67, e a compatibilidade do export com a API é a C3.

**Decisão:** seguir o plano. O modelo do projeto é o boosted tree do BigQuery ML,
treinado na C4 sobre a `gold_treino`, avaliado com `ML.EVALUATE`, registrado no
Vertex AI e exportado para a API (C5). O XGBoost local fica só na C2, como teste
de sinal.
