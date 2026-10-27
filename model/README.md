# model/

Frente C: exploração, limiar de "foco intenso", modelo e exportação.

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

Gerado por `model/sinal_modelo.py` em 2026-10-27 03:56 UTC. XGBoost local sobre a Gold de treino (`focos.gold_treino`): treino de out/2025 a ago/2026 e teste em set/2026, só focos com FRP, rótulo pelo limiar de `focos.limiar_frp`, matriz na ordem e na codificação da API (`model/pacote.py`, xgboost 2.1.3).

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

## Custos no GCP

Regra da Frente C: nada roda no GCP sem antes estimar o que vai ser
processado e quanto vai custar.

- **Antes de rodar:** dry-run (`DRY_RUN=1 bash sql/run_sql.sh arquivo.sql`, ou
  `dry_run=True` na API). Os scripts de `model/` já fazem isso e param se a
  consulta passar do limite (`LIMITE_GB_CONSULTA`, com `maximum_bytes_billed`).
- **Tarifas:** consulta no BigQuery, US$ 6,25 por TiB lido; criação de modelo no
  BigQuery ML, US$ 312,50 por TiB (10 GiB grátis por mês), 50 vezes mais cara.
- **Depois de rodar:** conferir `totalBytesBilled` do job.
- **Treino de modelos é local** (gratuito), como na C2.

### O que aconteceu na C3 (20/10/2026)

Um boosted tree de teste no BigQuery ML, com só 500 focos (56 KB), ficou
mais de 25 minutos na fase de treino e foi cancelado. Mesmo cancelado, o job
cobrou **47.081.062.400 bytes (43,8 GiB)** na tarifa do BigQuery ML, cerca de
US$ 10 a 14, conforme a cota grátis do mês. Os "bytes" do boosted tree não são
o tamanho dos dados: a estimativa crescia junto com o tempo de processamento do
treino, então o custo não tem relação com o volume e não dá para prever.

**Decisão:** a Frente C usa a reserva prevista no plano. O modelo é treinado com
XGBoost local sobre a mesma Gold de treino, salvo num arquivo que a API carrega
com a mesma versão do xgboost, e não com o `CREATE MODEL` do BigQuery ML. Com
isso, a C3 deixa de testar o export do BigQuery ML e passa a combinar com a
Frente D o formato do arquivo do modelo. O registro no Vertex AI, se feito,
usa esse artefato.

<!-- C3: início (gerado por model/teste_pacote_api.py) -->
## C3. Teste do pacote do modelo

Gerado por `model/teste_pacote_api.py` em 2026-10-27 04:02 UTC, com 500 focos reais de treino de `focos.gold_treino`. É a "exportação de brinquedo" do plano, adaptada: o modelo real é um XGBoost treinado fora do BigQuery ML (ver "Custos no GCP"), então a C3 testa o pacote que a Frente C gera contra o código da API da Frente D (`origin/frente-d/api`).

### Resultado

- **Versão do XGBoost:** a API fixa `xgboost-cpu==2.1.3` em `api/requirements.txt`; o pacote foi gerado com `xgboost 2.1.3` (iguais). O treino da Frente C usa a mesma versão (`model/requirements.txt`).
- **Carga:** a classe `Modelo` da API carregou o pacote (`foco_intenso_teste_v0`).
- **Codificação:** 500 de 500 vetores montados pela API iguais aos do treino (15 colunas).
- **Paridade:** 500 de 500 probabilidades iguais; maior diferença 0.0e+00. Passou.
- **Categorias:** valores fora do manifest: nenhum. Focos sem bioma na amostra: 0; intensos: 60 de 500.

### Passo a passo da preparação das variáveis (para a Frente D)

É o que a Gold de treino, `model/pacote.py` e `api/app/features.py` + `modelo.py` fazem:

1. `hora` = `EXTRACT(HOUR FROM data_hora_gmt)` e `mes` = `EXTRACT(MONTH FROM data_hora_gmt)`, em UTC.
2. `tipo_orbita` vem de `focos.satelites` (no pacote, `satelites.json`).
3. Vazio e -999 viram nulo em todas as numéricas; nulo entra no vetor como `NaN` (o XGBoost trata o ausente).
4. Categóricas em one-hot, uma coluna por categoria na ordem do manifest; nulo ou valor fora da lista deixa todas as colunas em 0.
5. O vetor segue a ordem de `variaveis` do `manifest.json`, e o Booster lê as colunas pela posição:

   0. `lat`
   1. `lon`
   2. `hora`
   3. `mes`
   4. `tipo_orbita=geoestacionario`
   5. `tipo_orbita=polar`
   6. `bioma=Amazônia`
   7. `bioma=Caatinga`
   8. `bioma=Cerrado`
   9. `bioma=Mata Atlântica`
   10. `bioma=Pampa`
   11. `bioma=Pantanal`
   12. `numero_dias_sem_chuva`
   13. `precipitacao`
   14. `risco_fogo`

### Para a Frente D

- O pacote real tem o mesmo formato, com `versao_modelo` = `foco_intenso_v1`, em `gs://<BUCKET>/modelos/foco_intenso/v1/`. Não há export do BigQuery ML: o `api/README.md` ("Ainda falta") e o status ("D5 depende de C3") podem ser atualizados.
- `bioma` é obrigatório no `schemas.py` da API, mas há focos sem bioma nos dados (perfil A1). O modelo aceita bioma nulo (todas as colunas de bioma em 0); se a API aceitar `None`, esses focos também podem ser pontuados.
<!-- C3: fim -->
