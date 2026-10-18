"""Validação e limpeza de um foco recebido pelo Pub/Sub.

Funções puras, sem Apache Beam, para poderem ser testadas com pytest e lidas
sem conhecer o pipeline. As regras são as mesmas da Silver histórica (SQL):
aparar espaços, converter tipos e tratar vazio e -999 como nulo em todas as
colunas numéricas.
"""

import datetime as dt
import json
from typing import Any

# =============================================================================
# Constantes
# =============================================================================
# Os 16 campos do CSV do INPE, na ordem do arquivo
COLUNAS_INPE = (
    "id",
    "lat",
    "lon",
    "data_hora_gmt",
    "satelite",
    "municipio",
    "estado",
    "pais",
    "municipio_id",
    "estado_id",
    "pais_id",
    "numero_dias_sem_chuva",
    "precipitacao",
    "risco_fogo",
    "bioma",
    "frp",
)
COLUNAS_FLOAT = ("lat", "lon", "numero_dias_sem_chuva", "precipitacao", "risco_fogo", "frp")
COLUNAS_INT = ("municipio_id", "estado_id", "pais_id")
COLUNAS_TEXTO = ("id", "satelite", "municipio", "estado", "pais", "bioma")
CAMPOS_OBRIGATORIOS = ("id", "lat", "lon", "data_hora_gmt", "satelite", "estado")

MARCADOR_INVALIDO_INPE = -999.0  # Valor que o INPE usa para "sem dado"

# Retângulo que contém o Brasil, ilhas oceânicas incluídas
LAT_MIN, LAT_MAX = -34.0, 5.5
LON_MIN, LON_MAX = -74.5, -28.5
RISCO_FOGO_MIN, RISCO_FOGO_MAX = 0.0, 1.0

FORMATOS_DATA_HORA = (
    "%Y-%m-%d %H:%M:%S",  # Formato do CSV do INPE
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
)
FORMATO_TIMESTAMP_BQ = "%Y-%m-%d %H:%M:%S.%f UTC"
ORIGEM = "streaming"
# =============================================================================


class FocoInvalidoError(Exception):
    """Mensagem que não pode virar uma linha da Silver. O texto é o motivo."""


def agora_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _texto(valor) -> str | None:
    """Converte para texto aparado; vazio vira None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def para_float(valor, campo) -> float | None:
    """Texto para float. Vazio e -999 viram None; texto não numérico é erro."""
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        numero = float(texto)
    except ValueError:
        raise FocoInvalidoError(f"numero_invalido:{campo}") from None
    if numero == MARCADOR_INVALIDO_INPE:
        return None
    return numero


def para_int(valor, campo) -> int | None:
    numero = para_float(valor, campo)
    if numero is None:
        return None
    if not numero.is_integer():
        raise FocoInvalidoError(f"inteiro_invalido:{campo}")
    return int(numero)


def para_data_hora(valor) -> dt.datetime:
    """Texto do INPE (GMT) para datetime com fuso UTC."""
    texto = _texto(valor)
    for formato in FORMATOS_DATA_HORA:
        try:
            return dt.datetime.strptime(texto, formato).replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            continue
    raise FocoInvalidoError("data_hora_invalida")


def para_instante_opcional(valor) -> dt.datetime | None:
    """publicado_em em ISO 8601; ausente ou inválido vira None (não rejeita o foco)."""
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        instante = dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=dt.timezone.utc)
    return instante.astimezone(dt.timezone.utc)


def formatar_timestamp_bq(instante) -> Any | None:
    return instante.astimezone(dt.timezone.utc).strftime(FORMATO_TIMESTAMP_BQ) if instante else None


def decodificar(dados) -> dict[Any, Any]:
    """Bytes da mensagem para dict. Rejeita JSON quebrado ou que não seja objeto."""
    try:
        foco = json.loads(dados.decode("utf-8") if isinstance(dados, bytes) else dados)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise FocoInvalidoError("json_invalido") from None
    if not isinstance(foco, dict):
        raise FocoInvalidoError("json_nao_e_objeto")
    return foco


def validar(foco) -> None:
    """
    Levanta FocoInvalidoError com o primeiro problema encontrado.

    O satélite não é conferido contra a tabela satelites: um satélite fora dela
    é aceito e só deixa de contar como intenso nos agregados (aggregation.py),
    porque sem a órbita não há limiar para comparar.
    """
    for campo in CAMPOS_OBRIGATORIOS:
        if _texto(foco.get(campo)) is None:
            raise FocoInvalidoError(f"campo_obrigatorio_ausente:{campo}")

    for campo in COLUNAS_FLOAT:
        para_float(foco.get(campo), campo)
    for campo in COLUNAS_INT:
        para_int(foco.get(campo), campo)
    para_data_hora(foco.get("data_hora_gmt"))

    lat = para_float(foco["lat"], "lat")
    lon = para_float(foco["lon"], "lon")
    if lat is None or lon is None:
        raise FocoInvalidoError("coordenada_ausente")
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        raise FocoInvalidoError("coordenada_fora_do_brasil")

    risco = para_float(foco.get("risco_fogo"), "risco_fogo")
    if risco is not None and not (RISCO_FOGO_MIN <= risco <= RISCO_FOGO_MAX):
        raise FocoInvalidoError("risco_fogo_fora_da_faixa")


def limpar(foco, instante_ingestao=None) -> dict[Any, Any]:
    """Foco já validado para uma linha da silver_focos_streaming."""
    data_hora = para_data_hora(foco.get("data_hora_gmt"))
    linha = {}
    for campo in COLUNAS_TEXTO:
        linha[campo] = _texto(foco.get(campo))
    for campo in COLUNAS_FLOAT:
        linha[campo] = para_float(foco.get(campo), campo)
    for campo in COLUNAS_INT:
        linha[campo] = para_int(foco.get(campo), campo)
    linha["data_hora_gmt"] = formatar_timestamp_bq(data_hora)
    linha["data_deteccao"] = data_hora.date().isoformat()
    linha["origem"] = ORIGEM
    linha["publicado_em"] = formatar_timestamp_bq(para_instante_opcional(foco.get("publicado_em")))
    linha["ingerido_em"] = formatar_timestamp_bq(instante_ingestao or agora_utc())
    return linha


def linha_de_erro(dados, atributos, motivo, instante=None) -> dict[str, Any]:
    """Linha da tabela streaming_erros."""
    if isinstance(dados, bytes):
        dados = dados.decode("utf-8", errors="replace")
    return {
        "mensagem_bruta": dados,
        "atributos": json.dumps(dict(atributos or {}), ensure_ascii=False),
        "motivo": motivo,
        "recebido_em": formatar_timestamp_bq(instante or agora_utc()),
    }
