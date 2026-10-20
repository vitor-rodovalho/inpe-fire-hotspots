# Evidências do streaming

Gerado pelo notebook `notebooks/02_streaming_evidence.ipynb` em 20/10/2026 00:53 UTC, sobre o dataset `focos` a partir de 2026-10-01. As consultas estão em `sql/evidence/`.

## Gold x Silver
- 4.543 de 4.543 janelas batem (situação ok); focos: 625.215 na gold e 625.215 na Silver.
- Janelas fora de ok: nenhuma.
- Até 6 gravações por janela e estado (a janela é gravada de novo quando chegam focos atrasados; vale a mais recente).

## Valores ausentes
- 625.215 focos de 12 satélites; 3,7% sem FRP (23.211).
- Satélites que nunca trazem FRP: METOP-B, METOP-C, MSG-03.
- Outras colunas sem valor: risco de fogo (15.976), dias sem chuva (20.120), precipitação (12.669).

## Erros
- 12.623 mensagens rejeitadas (1,98% das mensagens lidas): json_invalido (4.239), risco_fogo_fora_da_faixa (4.199), coordenada_fora_do_brasil (4.185).
- São cópias estragadas de propósito pelo replay (--fracao-invalidas); o foco original segue para a Silver.

## Janelas de 1 hora
- Estado e dia com mais focos: PARÁ, 08/10/2026, com 20 janelas e 26.799 focos.
- Janelas pelo horário da detecção, calculadas entre 19/10 10:00 e 19/10 10:00 UTC, durante o replay.

## Latência (publicação no Pub/Sub até a gravação na Silver)
- Mediana 824,47 s, p95 2.633,39 s e máximo 3.242,11 s, em 625.215 focos.
- Mediana por minuto entre 17,71 s e 2.692,92 s, em 44 minutos de publicação (19/10 07:26 a 19/10 12:54 UTC).

Total lido pelo notebook: 0,09 GB.
Arquivos desta execução: `gs://inpe-fire-hotspots-data/evidencias/streaming/2026-10-20_005335/`.
