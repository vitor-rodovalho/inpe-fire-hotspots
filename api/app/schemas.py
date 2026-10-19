"""Contrato da API: o que /predict recebe e o que devolve.

A entrada são as variáveis conhecidas no momento da detecção, com os nomes da
Silver. O FRP não entra, por isso a API aceita tanto um foco real quanto um
hipotético. Campos a mais (id, frp, municipio...) são ignorados, para que uma
linha da Silver possa ser enviada como está.

As faixas válidas são as mesmas do pipeline de streaming
(pipeline/focos_stream/cleaning.py). Fora delas, a resposta é 422.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Constantes (iguais às de pipeline/focos_stream/cleaning.py)
# =============================================================================
LAT_MIN, LAT_MAX = -34.0, 5.5
LON_MIN, LON_MAX = -74.5, -28.5
RISCO_FOGO_MIN, RISCO_FOGO_MAX = 0.0, 1.0
MARCADOR_INVALIDO_INPE = -999.0  # Valor que o INPE usa para "sem dado"

Bioma = Literal["Amazônia", "Caatinga", "Cerrado", "Mata Atlântica", "Pampa", "Pantanal"]
# =============================================================================


class FocoEntrada(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [
                {
                    "satelite": "NOAA-20",
                    "data_hora_gmt": "2026-10-14T18:42:00Z",
                    "lat": -9.51,
                    "lon": -56.20,
                    "bioma": "Amazônia",
                    "numero_dias_sem_chuva": 21,
                    "precipitacao": 0.0,
                    "risco_fogo": 0.97,
                }
            ]
        },
    )

    satelite: str = Field(min_length=1, description="Nome como aparece no CSV do INPE")
    data_hora_gmt: dt.datetime = Field(description="Horário da detecção; sem fuso, é lido como GMT")
    lat: float = Field(ge=LAT_MIN, le=LAT_MAX)
    lon: float = Field(ge=LON_MIN, le=LON_MAX)
    bioma: Bioma
    # Clima no ponto: podem faltar (o INPE manda -999 ou vazio), e aí viram nulo
    numero_dias_sem_chuva: float | None = Field(default=None, ge=0)
    precipitacao: float | None = Field(default=None, ge=0)
    risco_fogo: float | None = Field(default=None, ge=RISCO_FOGO_MIN, le=RISCO_FOGO_MAX)

    @field_validator("satelite", mode="before")
    @classmethod
    def _aparar_satelite(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("numero_dias_sem_chuva", "precipitacao", "risco_fogo", mode="before")
    @classmethod
    def _invalido_vira_nulo(cls, valor):
        """Mesma regra da Silver: vazio e -999 viram nulo."""
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        try:
            if float(valor) == MARCADOR_INVALIDO_INPE:
                return None
        except (TypeError, ValueError):
            pass  # O Pydantic recusa o valor com a mensagem padrão
        return valor

    @field_validator("data_hora_gmt")
    @classmethod
    def _para_utc(cls, valor: dt.datetime) -> dt.datetime:
        if valor.tzinfo is None:
            return valor.replace(tzinfo=dt.timezone.utc)
        return valor.astimezone(dt.timezone.utc)


class Previsao(BaseModel):
    probabilidade_intenso: float = Field(ge=0, le=1)
    intenso: bool
    versao_modelo: str


class Saude(BaseModel):
    status: Literal["ok"]
    versao_modelo: str
