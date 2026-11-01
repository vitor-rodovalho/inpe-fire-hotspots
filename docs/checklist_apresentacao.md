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
      consultas de `sql/demo/` e `https://<URL>/docs`.

## Durante a demo (parte da API, cerca de 1 minuto)

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
