# Notebooks

Exploração dos dados e obtenção de evidências. O que roda em produção
(crawler, SQL, pipeline, API) fica em scripts nas outras pastas. Os notebooks
só leem o que já está no BigQuery e no bucket.

| Notebook | O que responde | Pré-requisito |
|---|---|---|
| `01_data_profile.ipynb` | Volume, qualidade das 16 colunas, unicidade do id, satélites e órbitas, focos sem FRP, faixas, distribuição do FRP e arquivos diários | Crawler rodado e Bronze carregada |


## Como rodar

**BigQuery Studio (recomendado):** no console da GCP, BigQuery > Notebook >
Importar notebook, e escolher o arquivo `.ipynb`. Ajuste as constantes da
primeira célula de código para os valores de `config.env` e rode tudo.

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

Os gráficos (PNG) e o resumo (`data_profile.md`) ficam em `profile_output/`,
que não vai para o GitHub. Copie o resumo para `docs/data_profile.md` e os
gráficos selecionados para `docs/figuras/`.

Antes de fazer commit, limpe as saídas do notebook (Editar > Limpar todas as
saídas), para o diff ficar legível.
