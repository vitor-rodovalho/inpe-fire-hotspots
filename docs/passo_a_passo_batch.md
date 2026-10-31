# Passo a passo: Silver, view e Gold

Roda no Cloud Shell, na raiz do repositório. Primeiro um **teste com amostra**
num dataset à parte (`focos_teste`, cerca de 10% de ago e set/2026, centavos de
custo), depois o **dataset real**. O teste não toca em nada do `focos`.

O limiar de FRP não é calculado aqui: ele é da Frente C, que já o gravou em
`focos.limiar_frp` (202,1 MW geoestacionário e 28,4 MW polar, veja
`model/README.md`).

## 0. Preparação

```bash
cd ~/inpe-fire-hotspots            # Onde o repositório foi clonado
git fetch && git switch frente-a/batch && git pull
gcloud config set project inpe-fire-hotspots

# O limiar da Frente C precisa estar gravado (duas linhas)
bq query --use_legacy_sql=false 'SELECT tipo_orbita, ROUND(limiar, 1) AS limiar FROM focos.limiar_frp'
```

## 1. Teste com amostra (dataset `focos_teste`)

```bash
bq --location=us-central1 mk -d --description "Teste da Frente A" focos_teste
export DATASET_TESTE=focos_teste        # A partir daqui, tudo vai para focos_teste
```

Cada comando mostra o dataset no log (`dataset focos_teste`). Confira antes de seguir.

| # | Comando | O que conferir |
|---|---|---|
| 1 | `bash sql/run_sql.sh sql/teste/01_amostra_bronze.sql` | Duas linhas (2026-08-01 e 2026-09-01), com algumas dezenas de milhares de focos cada. Copia também `satelites` e `limiar_frp` |
| 2 | `bash sql/run_sql.sh sql/streaming/01_silver_focos_streaming.sql` | Sem erro. Cria a Silver de streaming vazia, que a view precisa |
| 3 | `bash sql/run_sql.sh sql/silver/01_silver_focos_historico.sql` | Só as linhas `bronze`, `repetido_por_id` (0) e `silver`, com `silver` = `bronze`. Uma linha `descartado` só aparece se algum foco foi descartado |
| 4 | `bash sql/run_sql.sh sql/silver/02_vw_focos_unificada.sql` | Sem erro (a view não imprime resultado) |
| 5 | `bash sql/run_sql.sh sql/gold/01_gold_treino.sql` | Quatro linhas (treino e teste, por órbita). No teste só agosto entra no treino, então a % de positivos fica perto de 10%, mas não exatamente |
| 6 | `bash sql/run_sql.sh sql/silver/03_check_silver.sql` | `situacao = ok` em todas as linhas |
| 7 | `bash sql/run_sql.sh sql/demo/06_count_by_origin.sql` | Uma linha `batch`. Não há `streaming` porque a Silver de streaming do teste está vazia |

Terminou? Desligue o modo teste e apague o dataset:

```bash
unset DATASET_TESTE
bq rm -r -f -d inpe-fire-hotspots:focos_teste
```

Para um teste maior, troque `UM_EM_CADA` no topo de `sql/teste/01_amostra_bronze.sql`
(1 = todos os focos dos dois meses).

## 2. Dataset real (`focos`)

Só depois de o teste passar. Confirme que `DATASET_TESTE` não está definida:

```bash
echo "DATASET_TESTE=[${DATASET_TESTE:-}]"       # Deve mostrar []
```

```bash
bash sql/run_sql.sh sql/silver/01_silver_focos_historico.sql      # A5, lê a Bronze inteira
bash sql/run_sql.sh sql/silver/02_vw_focos_unificada.sql          # A8
bash sql/run_sql.sh sql/gold/01_gold_treino.sql                   # A7
bash sql/run_sql.sh sql/silver/03_check_silver.sql
bash sql/run_sql.sh sql/demo/06_count_by_origin.sql
bash sql/run_sql.sh sql/demo/07_streaming_last_days.sql
```

Valores esperados no real. Os da Gold são os mesmos que a Frente C mediu na
etapa C2 (`model/README.md`), porque a Gold monta o mesmo conjunto:

| Passo | Esperado |
|---|---|
| Silver | `bronze` = 3.342.337, `repetido_por_id` = 0 e `silver` = 3.342.337. O perfil não achou nada a descartar; se houver descarte, o resumo diz o motivo e a Gold fica um pouco menor que a da C2 |
| Gold, treino | 2.530.560 focos, 10,0% positivos |
| Gold, teste | 756.172 focos, 10,8% positivos |
| Conferência | `situacao = ok` em todas as linhas; 20 colunas iguais às da Silver de streaming |
| Demo 06 | `batch` de 2025-10-01 a 2026-09-30; `streaming` a partir de 2026-10-01 |
| Demo 07 | Os 3 dias mais recentes do streaming |

## 3. Evidências para os slides (A9)

```bash
# Bytes estimados: o mesmo agrupamento com filtro de 1 dia e sem filtro
DRY_RUN=1 bash sql/run_sql.sh sql/evidence/06_bytes_one_day.sql
DRY_RUN=1 bash sql/run_sql.sh sql/evidence/07_bytes_whole_period.sql

# Consulta sem filtro de data na Silver: o BigQuery precisa recusar
bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM focos.silver_focos_historico'

# Tamanho total dos arquivos do INPE no bucket (pendência do A2)
gsutil du -sh gs://inpe-fire-hotspots-data/raw/mensal gs://inpe-fire-hotspots-data/raw/diario
```

Copie os números para [batch_evidence.md](batch_evidence.md).

## 4. Depois

- **Frente C:** avise que a `gold_treino` está pronta e confere com a C2.
- **Frente B:** se o job do Dataflow ainda não foi reiniciado depois que a Frente C gravou o limiar, `qtd_intensos` continua nulo nos agregados (`pipeline/drain.sh` e depois `pipeline/deploy.sh`).
- Se o limiar mudar, rode de novo a Gold.

## Se der erro

| Mensagem | Causa e saída |
|---|---|
| `Modo teste desligado: rode com DATASET_TESTE=...` | Você rodou `sql/teste/01` sem `export DATASET_TESTE`. É a trava que protege a Bronze real. Defina a variável e rode de novo |
| `limiar_frp sem todas as órbitas` | `limiar_frp` está vazia ou incompleta. No real, a Frente C grava com `python3 model/exploracao_limiar.py --gravar`; no teste, rode de novo o passo 1 |
| `Cannot query over table ... without a filter over column(s) 'data_deteccao'` | Consulta direta na Silver sem filtro de data. É o esperado na evidência do passo 3; em outro caso, acrescente `WHERE data_deteccao ...` |
| `Not found: Table ...silver_focos_streaming` | Faltou criar a Silver de streaming. No teste, é o passo 2; no real, `bash sql/run_sql.sh sql/streaming/*.sql` |
| `Not found: Table ...bronze_focos_mensal`, `satelites` ou `limiar_frp` | No real, rode antes `sql/bronze/*` e `sql/reference/*`. No teste, o passo 1 |
| Qualquer erro de sintaxe | Mande a mensagem completa, com o número da linha |
