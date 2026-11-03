# Checklist do dia da apresentação

A parte ao vivo vale 60% da nota e o limite é de 10 minutos. Tudo roda no
projeto de verdade, então cada passo abaixo foi pensado para não deixar nada
ligado à toa.

## 1 hora antes

- [ ] Abrir o Cloud Shell no projeto `inpe-fire-hotspots` e atualizar o código:
      `cd inpe-fire-hotspots && git pull`.
- [ ] Ligar o Dataflow com antecedência, porque ele leva alguns minutos para
      subir: `bash pipeline/deploy.sh` (custa de US$ 0,20 a 0,30 por hora).
- [ ] Escolher um período de replay que **ainda não foi usado** com este job
      (replay voltando no tempo faz os focos caírem fora das janelas).

## 15 minutos antes

- [ ] Deixar a API sem cold start: `bash api/instancias_minimas.sh 1`.
- [ ] Conferir a API inteira em menos de 1 minuto: `python3 api/testar_api.py`
      (token, paridade, erros 422 e latência). Os scripts acham o token
      sozinhos (`config.local.env` ou o próprio Cloud Run).
- [ ] Ligar o replay e confirmar que a Silver de streaming está recebendo focos.
- [ ] Rodar a demo uma vez: `python3 scripts/demo.py`. Se o BigQuery falhar,
      o plano B é `python3 scripts/demo.py --offline`.
- [ ] Deixar abertos: o grafo do job no console do Dataflow, o BigQuery com as
      consultas de `sql/demo/` e `https://api-foco-intenso-21360820866.us-central1.run.app/docs`.

## Durante a demo: pipelines batch e streaming (cerca de 4 minutos)

Deixar o replay rodando em um terminal e as consultas em outro (ou no console
do BigQuery). Cada consulta pode ser rodada de novo para mostrar os números
mudando.

- [ ] **Gerador → Pub/Sub.** Mostrar o terminal do replay publicando
      (`bash ingestion/run.sh replay_pubsub --inicio <dia novo> --fracao-invalidas 0.02`)
      e uma mensagem JSON de exemplo (`pipeline/tests/data/sample_hotspot.json`).
- [ ] **Processador.** No console do Dataflow, o grafo do job `focos-streaming`:
      Validar → Limpar → Deduplicar → Silver e Janela de 1 h → agregados.
- [ ] **Persistência em tempo real.**
      `bash sql/run_sql.sh sql/demo/01_streaming_per_minute.sql` (focos por
      minuto crescendo) e `sql/demo/02_streaming_latency.sql` (Pub/Sub até o
      BigQuery).
- [ ] **Limpeza.** `sql/demo/05_errors_by_reason.sql`: as mensagens inválidas
      foram separadas por motivo, sem perder o foco original.
- [ ] **Agregados.** `sql/demo/03_recent_aggregates.sql` (últimas janelas por
      estado) e `sql/demo/04_check_aggregates.sql` (Dataflow = SQL, `ok`).
- [ ] **Batch + streaming juntos.** `sql/demo/06_count_by_origin.sql`: `batch`
      parado e `streaming` subindo na `vw_focos_unificada`, e
      `sql/demo/07_streaming_last_days.sql` com o dia do replay crescendo.
- [ ] **Papel de cada pipeline.** O batch (mensais → Bronze → Silver → Gold)
      ensina o modelo; o streaming aplica e avalia:
      `sql/demo/08_model_monitoring.sql` mostra as métricas do modelo nos focos
      que acabaram de chegar, ao lado do mês de teste.

## Durante a demo: API no Cloud Run (cerca de 1 minuto)

- [ ] `python3 scripts/demo.py`: foco com FRP (previsão contra o real), foco
      sem FRP (a estimativa) e foco hipotético, com o tempo de cada resposta.
- [ ] Se sobrar tempo, em `/docs`: uma chamada sem token (401), depois
      **Authorize** com o token e uma com entrada inválida (422). Ter o token
      à mão: `cd api && python3 -c "from cliente_api import ler_token; print(ler_token())"`.

## Logo depois

- [ ] Desligar o Dataflow: `bash pipeline/drain.sh`.
- [ ] Voltar a API para 0 instâncias: `bash api/instancias_minimas.sh 0`.
- [ ] No dia seguinte, conferir em Faturamento → Relatórios que nada ficou
      ligado.

## Plano B

- Vídeo da demo completa, gravado no último ensaio.
- `scripts/demo.py --offline`: chama a API com focos fixos, sem BigQuery.
- `docs/api_evidence.md`: paridade e latência medidas no Cloud Run.
