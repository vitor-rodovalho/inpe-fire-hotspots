# Ingestão

Os dois caminhos pelos quais os dados do INPE entram no projeto. Os dois
trabalham com os mesmos CSVs e dividem as constantes e a leitura em `common.py`.

| Arquivo | Caminho | O que faz |
|---|---|---|
| `download_inpe.py` | INPE -> Cloud Storage | Baixa os CSVs mensais (histórico, batch) e diários (base do streaming) |
| `replay_pubsub.py` | Cloud Storage -> Pub/Sub | Publica os focos dos diários em ordem de detecção, simulando o tempo real (produtor do streaming) |
| `common.py` | - | Nomes do bucket, das pastas e dos arquivos, e leitura de CSV local ou `gs://` |
| `run.sh` | - | Carrega `config.env` e roda um dos scripts |

Os dois scripts também rodam sem nuvem nenhuma, gravando numa pasta local.
Veja [Teste sem nuvem](#teste-sem-nuvem).


## Instalação

```bash
pip install -r ingestion/requirements.txt
```


## Download do INPE (`download_inpe.py`)

| Tipo | Período (em `config.env`) | Destino |
|---|---|---|
| Mensal (histórico, batch) | `MES_INICIO` a `MES_FIM` | `gs://<BUCKET>/raw/mensal/` |
| Diário (streaming) | `DIA_INICIO` até `DIA_FIM` (vazio = ontem) | `gs://<BUCKET>/raw/diario/` |

```bash
bash ingestion/run.sh download_inpe --somente-listar   # Mostra o que seria baixado
bash ingestion/run.sh download_inpe                    # Mensal e diário
bash ingestion/run.sh download_inpe --tipo diario      # Só os diários
bash ingestion/run.sh download_inpe --tipo mensal --inicio 2026-08   # Só um mês
```

| Opção | Padrão | Para quê |
|---|---|---|
| `--tipo` | `todos` | `mensal`, `diario` ou `todos` |
| `--inicio`, `--fim` | Período do `config.env`, `--fim` = `--inicio` | Outro período: `AAAA-MM` com `--tipo mensal`, `AAAA-MM-DD` com `--tipo diario` |
| `--destino` | O bucket | Pasta local no lugar do bucket, com as mesmas subpastas |
| `--forcar` | - | Baixa de novo mesmo o que já está no destino |
| `--somente-listar` | - | Mostra o que seria baixado, sem baixar |

Rodar de novo não duplica nada: um arquivo só é baixado outra vez se o
tamanho dele no INPE mudou.

Se o INPE não responder, o script tenta de novo até 4 vezes, com espera
crescente entre as tentativas. Um arquivo que ainda assim falhar aparece como
`[falhou]` e os outros continuam. Depois de 3 falhas seguidas, o script para,
porque o INPE provavelmente está fora do ar. O envio ao bucket vai em pedaços
de 8 MB, e um pedaço que falha é reenviado sozinho. Se a conexão continuar
caindo, o arquivo também aparece como [falhou]. Em qualquer caso, basta rodar o
mesmo comando de novo mais tarde. Se o INPE publicar um arquivo zipado, o script
extrai o CSV antes de enviar. Ao final, ele reescreve
`gs://<BUCKET>/raw/manifesto/arquivos.csv` com o número de linhas de cada
arquivo, que a carga da Bronze usa para conferir se nenhuma linha se perdeu.


### Depois do download: carga da Bronze

```bash
bash sql/run_sql.sh \
  sql/bronze/01_external_tables.sql \
  sql/bronze/02_bronze_focos_mensal.sql \
  sql/bronze/03_check_bronze.sql
```

A carga está certa quando a coluna `situacao` da conferência é `ok` em todos
os arquivos. Com a Bronze carregada, gere as tabelas de referência:

```bash
bash sql/run_sql.sh sql/reference/*.sql
```

A tabela `satelites` sai da própria Bronze: cada satélite que aparece nos CSVs
é classificado como geoestacionário ou polar pela quantidade de horas com focos
num mesmo dia (detalhes no cabeçalho de `sql/reference/01_satelites.sql`).
Em seguida, `sql/bronze/04_data_profile.sql` mostra os satélites,
a parcela sem FRP e os valores ausentes. A versão completa, com gráficos, está
em `notebooks/01_data_profile.ipynb`.


## Replay para o Pub/Sub (`replay_pubsub.py`)

O INPE não oferece um fluxo de eventos, só arquivos. O replay lê os diários do
bucket, ordena os focos pelo horário da detecção e publica cada um no tópico.
Entre um horário e o seguinte, espera o intervalo real dividido pelo fator de
aceleração. Com o fator padrão (600), uma hora de detecções passa em 6
segundos e um dia inteiro em cerca de 2 minutos e meio.

```bash
# Ver o plano sem publicar: quantos focos, período e duração estimada
bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fim 2026-10-03 --somente-contar

# Replay normal (deixe o job do Dataflow ligado antes)
bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fim 2026-10-03

# Com cópias inválidas de 2% dos focos, para a tabela streaming_erros
bash ingestion/run.sh replay_pubsub --inicio 2026-10-04 --fracao-invalidas 0.02

# Teste rápido: 200 focos, um a cada 0,1 s, mais 5% de cópias inválidas
bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --max-mensagens 200 \
  --intervalo-fixo 0.1 --fracao-invalidas 0.05
```

| Opção | Padrão | Para quê |
|---|---|---|
| `--inicio`, `--fim` | (obrigatório), `--fim` = `--inicio` | dias lidos de `raw/diario/` |
| `--arquivos` | - | CSVs locais ou `gs://` no lugar dos dias |
| `--fator` | 600 | Aceleração do tempo |
| `--espera-maxima` | 5 s | Teto de uma espera, para madrugadas sem foco não travarem a demo |
| `--intervalo-fixo` | - | Ignora o tempo real e espera um intervalo fixo entre mensagens |
| `--max-mensagens` | - | Para depois de N focos |
| `--fracao-invalidas` | 0 | Fração dos focos que ganha também uma cópia estragada (veja abaixo) |
| `--somente-contar` | - | Mostra o plano sem publicar |
| `--permitir-voltar` | - | Aceita um período anterior ao último publicado |
| `--saida` | - | Grava as mensagens num arquivo `.jsonl` em vez de publicar |


### Mensagens inválidas

Com `--fracao-invalidas 0.05`, cerca de 5% dos focos são publicados duas vezes:
primeiro o foco real, intacto, e logo depois uma cópia estragada de propósito
(JSON quebrado, coordenada fora do Brasil ou `risco_fogo` fora de 0 a 1). O foco
real segue para a Silver e para os agregados como qualquer outro, então
nenhum dado se perde. A cópia vai para `streaming_erros`, com o `id` terminado
em `-invalida` nos atributos, o que permite separá-la numa consulta.


### Nunca voltar no tempo

O Dataflow agrupa os focos em janelas de 1 hora pelo horário da detecção. Um
foco com horário anterior a uma janela já fechada é descartado dos agregados.
Por isso o replay guarda o último horário publicado em
`ingestion/.replay_state.json` e se recusa a começar antes dele. Para repetir
um período (por exemplo, num novo ensaio), reinicie o job e use
`--permitir-voltar`:

```bash
bash pipeline/drain.sh && bash pipeline/deploy.sh
bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --permitir-voltar
```


## Teste sem nuvem

Para conferir o download, o replay e o pipeline sem tocar no bucket, no
Pub/Sub nem no BigQuery. Tudo fica na pasta `dados/` (`PASTA_LOCAL` em
`config.env`), que não vai para o Git, e só o download usa a internet. Roda
no WSL, no Linux, no Mac ou no Cloud Shell, sempre a partir da raiz do
repositório.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r ingestion/requirements.txt -r pipeline/requirements-dev.txt

# 1. Um mês e um dia do INPE para dados/raw/ (com manifesto em dados/raw/manifesto/)
bash ingestion/run.sh download_inpe --destino dados --tipo mensal --inicio 2026-08
bash ingestion/run.sh download_inpe --destino dados --tipo diario --inicio 2026-09-30

# 2. Mensagens do dia num arquivo, em vez do Pub/Sub
bash ingestion/run.sh replay_pubsub --arquivos dados/raw/diario/*.csv \
  --fracao-invalidas 0.05 --saida dados/mensagens.jsonl

# 3. Pipeline lendo esse arquivo e gravando as três tabelas em dados/pipeline/
bash pipeline/run_local.sh --offline
```

O que conferir:

- Download: o número de linhas de cada arquivo em `dados/raw/manifesto/arquivos.csv`
  e os CSVs abertos numa planilha. Ao lado de cada CSV, um `.meta.json` guarda de
  onde ele veio. Rodar de novo não baixa o que não mudou.
- Replay: uma mensagem por linha em `dados/mensagens.jsonl`, no formato
  `{"data": "<corpo>", "attributes": {"id": ..., "ts_evento": ...}}`.
- Pipeline: `silver_focos_streaming.jsonl` com um foco por `id` (os repetidos
  somem), `streaming_erros.jsonl` só com as cópias `-invalida` e
  `gold_agregados_janela.jsonl` com uma linha por hora e estado. Os limiares de
  `pipeline/references_example.json` são fictícios, então `qtd_intensos` só
  serve para ver a conta funcionando. A última linha do pipeline conta os
  focos de satélite fora da tabela desse JSON, que entram na Silver mas não
  contam como intensos; com os satélites de hoje, deve dar 0.

No WSL, se o `python3 -m venv` reclamar, instale o pacote com `sudo apt install python3-venv`.
