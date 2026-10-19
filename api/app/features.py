"""Transforma a entrada da API nas variáveis do modelo.

Precisa calcular tudo exatamente como a Gold de treino (sql/gold/), senão o
modelo recebe na API algo diferente do que viu no treino. O arquivo de
paridade (model/paridade.jsonl) é o teste de que as duas pontas concordam.

  Variável      Na Gold                              Aqui
  hora          EXTRACT(HOUR FROM data_hora_gmt)     data_hora_gmt.hour, em UTC
  mes           EXTRACT(MONTH FROM data_hora_gmt)    data_hora_gmt.month, em UTC
  tipo_orbita   JOIN focos.satelites USING satelite  satelites.json do pacote
"""

from typing import Any

from .schemas import FocoEntrada


def preparar_variaveis(foco: FocoEntrada, tipo_orbita: str) -> dict[str, Any]:
    """Devolve as variáveis do modelo, com os nomes das colunas da Gold."""
    return {
        "lat": foco.lat,
        "lon": foco.lon,
        "hora": foco.data_hora_gmt.hour,
        "mes": foco.data_hora_gmt.month,
        "tipo_orbita": tipo_orbita,
        "bioma": foco.bioma,
        "numero_dias_sem_chuva": foco.numero_dias_sem_chuva,
        "precipitacao": foco.precipitacao,
        "risco_fogo": foco.risco_fogo,
    }
