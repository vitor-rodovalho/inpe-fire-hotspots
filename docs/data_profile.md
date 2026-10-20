# Perfil dos dados

Gerado pelo notebook `notebooks/01_data_profile.ipynb` sobre `inpe-fire-hotspots.focos.bronze_focos_mensal`.

## Volume
- 3.342.337 focos em 12 meses.
- Focos fora do mês do próprio arquivo: 0.

## Colunas
- Colunas com vazio ou -999 (% dos focos): numero_dias_sem_chuva (3.03%), precipitacao (1.79%), risco_fogo (2.47%), frp (1.66%).
- Colunas numéricas com texto que não converte: nenhum.
- Colunas com espaços sobrando: lat, lon.
- Textos com acento quebrado: 0.
- Estados distintos: 27; biomas: Cerrado, Amazônia, Caatinga, Mata Atlântica, Pantanal, Pampa, None.

## Unicidade
- O id é único: a deduplicação pode usar só o id.

## Satélites e FRP
- Satélites: NOAA-20, NOAA-21, GOES-19, NPP-375, NPP-375D, AQUA_M-T, TERRA_M-M, TERRA_M-T, METOP-B, METOP-C, AQUA_M-M, MSG-03.
- Sem órbita na tabela satelites: nenhum.
- Nunca trazem FRP: METOP-B, METOP-C, MSG-03.
- Focos sem FRP no histórico: 1.7% (peso da justificativa 1).
- Limiar candidato P90 (treino até 2026-08): geoestacionario = 202.2 MW, polar = 28.4 MW.

## Streaming
- Rejeição estimada pelas regras de validação: até 0.0% dos focos.
- Arquivos diários: 18 dias, 625.215 focos.
- Focos sem FRP nos diários: 3.7% (histórico: 1.7%).
- Focos dos diários de satélite fora da tabela de órbitas (aceitos, sem contar como intensos): 0.

Total lido pelo notebook: 2.17 GB.
