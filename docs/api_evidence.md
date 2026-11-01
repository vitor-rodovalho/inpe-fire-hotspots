# Evidências da API (Frente D)

Gerado por `api/testar_api.py` em 2026-11-01 00:27 UTC, contra `https://api-foco-intenso-21360820866.us-central1.run.app`.

| Teste | Resultado |
|---|---|
| Modelo carregado (`/health`) | `foco_intenso_v1` |
| Paridade com o `ML.PREDICT` (`model/paridade.jsonl`) | 50 de 50 iguais até a 4ª casa (maior diferença 5.0e-05) |
| Entradas inválidas recusadas com 422 | 4 de 4 |
| Primeira chamada (`/health`, pode incluir cold start) | 200 ms |
| Latência de `/predict`, 50 chamadas | mediana 211 ms, p95 230 ms, máximo 255 ms |

A latência é medida no cliente, com a rede. O tempo dentro da API vem no cabeçalho `X-Tempo-Processamento-Ms` de cada resposta.
