# Notebooks

Exploração dos dados e obtenção de evidências. O que roda em produção
(crawler, SQL, pipeline, API) fica em scripts nas outras pastas. Os notebooks
só leem o que já está no BigQuery e no bucket.

| Notebook | O que responde | Pré-requisito |
|---|---|---|
| `01_data_profile.ipynb` | Volume, qualidade das 16 colunas, unicidade do id, satélites e órbitas, focos sem FRP, faixas, distribuição do FRP e arquivos diários | Crawler rodado e Bronze carregada |
| `02_streaming_evidence.ipynb` | Gold x Silver, valores ausentes por satélite, erros por motivo, janelas de 1 hora de um dia e latência por minuto, com as consultas de `sql/evidence/` | Replay publicado e job drenado (ou 2 minutos depois do fim do replay) |


## Como rodar

**BigQuery Studio (recomendado):** no console da GCP, BigQuery > Notebook >
Importar notebook, e escolher o arquivo `.ipynb`.

- No notebook 01, ajuste as constantes da primeira célula de código para os
  valores de `config.env` e rode tudo.
- O notebook 02 não precisa de ajuste: ele clona o repositório público e lê
  `config.env` e `sql/evidence/` de lá. Por isso, as consultas precisam estar
  no `main` do GitHub antes.
- Na primeira vez, o console pode pedir para ativar APIs (Dataform e Vertex AI,
  por exemplo). O ambiente de execução do notebook é cobrado enquanto fica
  ligado; encerre-o ao terminar.

**Na máquina:**

```bash
pip install -r notebooks/requirements.txt
gcloud auth application-default login
cd notebooks && jupyter lab
```

Aberto de dentro do repositório, o notebook lê `../config.env` sozinho.


## Custo

Cada consulta passa antes por um dry run e não roda se for ler mais que
`LIMITE_GB_POR_CONSULTA`. O total lido aparece no fim do notebook.


## Saídas

Cada execução grava numa pasta própria, com a data e a hora (UTC) no nome, e
copia essa pasta para o bucket. Rodar de novo não apaga nem sobrescreve nada.

| Notebook | Pasta local | Cópia no bucket |
|---|---|---|
| 01 | `profile_output/<execução>/` | `gs://<BUCKET>/evidencias/perfil/<execução>/` |
| 02 | `streaming_output/<execução>/` | `gs://<BUCKET>/evidencias/streaming/<execução>/` |

As pastas locais não vão para o GitHub. No BigQuery Studio, elas ficam no
ambiente de execução e somem quando ele é encerrado; a cópia no bucket fica.
Para não enviar ao bucket, mude `ENVIAR_PARA_BUCKET` para `False` na primeira
célula de código.

Copie o resumo do notebook 01 para `docs/data_profile.md` e os gráficos
selecionados para `docs/figuras/`.

Antes de fazer commit, limpe as saídas do notebook (Editar > Limpar todas as
saídas), para o diff ficar legível.
