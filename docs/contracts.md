# Contratos entre as frentes

Nomes e formatos que mais de uma frente usa. Mudar qualquer item exige avisar
quem consome. Os valores concretos ficam em `config.env`.

## Recursos na GCP

| Recurso | Nome | Constante em `config.env` |
|---|---|---|
| Região de tudo | `us-central1` | `REGIAO` |
| Bucket | `gs://<PROJECT_ID>-data` | `BUCKET` |
| Dataset BigQuery | `focos` | `DATASET` |
| Tópico Pub/Sub | `focos-replay` | `TOPICO` |
| Assinatura do Dataflow | `focos-replay-dataflow` | `ASSINATURA` |
| Job do Dataflow | `focos-streaming` | `DATAFLOW_JOB` |
| Serviço do Cloud Run | `api-foco-intenso` | `CLOUD_RUN_SERVICO` |
| Conta de serviço do Dataflow | `sa-dataflow-focos` | `SA_DATAFLOW` |
| Conta de serviço da API | `sa-api-foco-intenso` | `SA_API` |
| Data de corte batch/streaming | `2026-09-01` | `DATA_CORTE` |

Pastas do bucket: `raw/mensal/`, `raw/diario/`, `raw/manifesto/`,
`dataflow/tmp/`, `dataflow/staging/`, `modelos/foco_intenso/`.


## Mensagem do Pub/Sub (replay -> Dataflow)

Um foco por mensagem.

**Corpo:** JSON com as 16 chaves do CSV do INPE, com os nomes originais e os
valores como vieram (texto, sem limpeza), mais `publicado_em`.

```json
{
  "id": "a1b2c3", "lat": "-9.51", "lon": "-56.20",
  "data_hora_gmt": "2026-09-30 18:40:00", "satelite": "GOES-19",
  "municipio": "ALTA FLORESTA", "estado": "MATO GROSSO", "pais": "Brasil",
  "municipio_id": "5100250", "estado_id": "51", "pais_id": "33",
  "numero_dias_sem_chuva": "21", "precipitacao": "0.0", "risco_fogo": "0.97",
  "bioma": "Amazônia", "frp": "35.2",
  "publicado_em": "2026-10-16T18:00:00.123+00:00"
}
```

**Atributos (obrigatórios):**

| Atributo | Conteúdo | Para quê |
|---|---|---|
| `id` | O mesmo `id` do corpo | Deduplicação |
| `ts_evento` | Horário da detecção em RFC 3339, por exemplo `2026-09-30T18:40:00Z` | Tempo do evento nas janelas do Beam |

Sem `ts_evento` (ou com valor fora do formato) o Dataflow não consegue ler a
mensagem. O replay nunca deve voltar no tempo com o job ligado: focos com
horário anterior a uma janela já fechada são descartados dos agregados.

**Cópias inválidas de teste:** com `--fracao-invalidas`, o replay publica, além
do foco real, uma cópia estragada dele com o atributo `id` terminado em
`-invalida`. Nenhum foco real é substituído.

**Arquivo local (teste sem nuvem):** `replay_pubsub.py --saida` grava as mesmas
mensagens num `.jsonl`, uma por linha, como
`{"data": "<corpo>", "attributes": {"id": "...", "ts_evento": "..."}}`.
`pipeline/run_local.sh --offline` lê esse arquivo.


## Regras de limpeza (iguais no SQL da Silver e no Beam)

- Aparar espaços de todos os campos.
- Vazio e `-999` viram `NULL` em todas as colunas numéricas.
- `data_deteccao = DATE(data_hora_gmt)`, que é a coluna de partição.
- `origem` = `'batch'` ou `'streaming'`.

Rejeitados pelo streaming (vão para `streaming_erros` com o motivo): JSON
quebrado, campo obrigatório ausente (`id`, `lat`, `lon`, `data_hora_gmt`,
`satelite`, `estado`), número ou data que não se converte, coordenada fora do
Brasil e `risco_fogo` fora de 0 a 1.

Um satélite fora da tabela `satelites` não é motivo de rejeição: o foco entra
na Silver e conta em `qtd_focos` e `frp_medio`, mas não em `qtd_intensos`,
porque sem a órbita não há limiar para comparar. O Dataflow conta esses focos
no contador `satelite_fora_da_tabela`.


## Tabelas de Streaming (criadas em `sql/streaming/`)

| Tabela | Partição | Uma linha por |
|---|---|---|
| `silver_focos_streaming` | `data_deteccao` (filtro obrigatório) | Foco válido |
| `streaming_erros` | `DATE(recebido_em)` | Mensagem rejeitada |
| `gold_agregados_janela` | `DATE(inicio_janela)` (filtro obrigatório) | Janela de 1 h e estado |

O esquema da `silver_focos_streaming` é idêntico ao da `silver_focos_historico`
(Frente A): as 16 colunas do INPE tipadas, mais `data_deteccao`, `origem`,
`publicado_em` e `ingerido_em`.


## Referências (criadas em `sql/reference/`, depois da carga da Bronze)

- `satelites (satelite, tipo_orbita, max_horas_num_dia, dias_com_focos,
  primeiro_dia, ultimo_dia, gerado_em)`: gerada da Bronze, com a órbita
  classificada pela quantidade de horas com focos num mesmo dia
  (`geoestacionario` ou `polar`). Lida pelo Dataflow ao subir e pela API.
- `limiar_frp (tipo_orbita, limiar, percentil, calculado_em)`: lida pelo Dataflow ao subir.

Depois de mudar uma delas, reinicie o job (`pipeline/drain.sh` e
`pipeline/deploy.sh`).
