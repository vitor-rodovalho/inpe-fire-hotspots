# Evidências da API (Frente D)

Gerado por `api/testar_api.py` em 2026-11-01 01:08 UTC, contra `https://api-foco-intenso-6m75iwripa-uc.a.run.app`.

| Teste | Resultado |
|---|---|
| Modelo carregado (`/health`) | `foco_intenso_v1` |
| `/predict` sem token / com token errado | 401 / 401 (esperado 401) |
| Paridade com o `ML.PREDICT` (`model/paridade.jsonl`) | 50 de 50 iguais até a 4ª casa (maior diferença 5.0e-05) |
| Entradas inválidas recusadas com 422 | 4 de 4 |
| Primeira chamada (`/health`, pode incluir cold start) | 109 ms |
| Latência de `/predict`, 50 chamadas | mediana 134 ms, p95 217 ms, máximo 245 ms |

A latência é medida no cliente, com a rede. O tempo dentro da API vem no cabeçalho `X-Tempo-Processamento-Ms` de cada resposta.
