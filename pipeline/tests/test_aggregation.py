"""Testes da conta feita em cada janela e estado."""

from typing import Any

from focos_stream import aggregation as a

SATELITES = {"GOES-19": "geoestacionario", "MSG-03": "geoestacionario", "NOAA-20": "polar"}
LIMIARES = {"geoestacionario": 50.0, "polar": 30.0}


def somar(focos, limiares=LIMIARES) -> dict[str, Any]:
    acumulador = a.acumulador_vazio()
    for foco in focos:
        a.adicionar(acumulador, foco, SATELITES, limiares)
    return acumulador


FOCOS = [
    {"satelite": "GOES-19", "frp": 60.0},  # Intenso (acima de 50)
    {"satelite": "GOES-19", "frp": 10.0},
    {"satelite": "MSG-03", "frp": None},  # Sem FRP
    {"satelite": "NOAA-20", "frp": 35.0},  # Intenso (acima de 30)
]


def test_conta_focos_sem_frp_media_e_intensos() -> None:
    resultado = a.resultado(somar(FOCOS), ha_limiares=True)
    assert resultado == {"qtd_focos": 4, "qtd_sem_frp": 1, "frp_medio": 35.0, "qtd_intensos": 2}


def test_mesclar_da_o_mesmo_que_somar_tudo_junto() -> None:
    partes = [somar(FOCOS[:1]), somar(FOCOS[1:3]), somar(FOCOS[3:])]
    assert a.mesclar(partes) == somar(FOCOS)


def test_sem_limiares_intensos_sai_nulo() -> None:
    resultado = a.resultado(somar(FOCOS, limiares={}), ha_limiares=False)
    assert resultado["qtd_intensos"] is None
    assert resultado["qtd_focos"] == 4


def test_janela_so_com_focos_sem_frp_tem_media_nula() -> None:
    resultado = a.resultado(somar([{"satelite": "MSG-03", "frp": None}]), ha_limiares=True)
    assert resultado == {"qtd_focos": 1, "qtd_sem_frp": 1, "frp_medio": None, "qtd_intensos": 0}


def test_satelite_fora_da_tabela_conta_mas_nao_e_intenso() -> None:
    resultado = a.resultado(somar([{"satelite": "SATELITE-NOVO", "frp": 500.0}]), ha_limiares=True)
    assert resultado == {"qtd_focos": 1, "qtd_sem_frp": 0, "frp_medio": 500.0, "qtd_intensos": 0}


def test_frp_igual_ao_limiar_nao_e_intenso() -> None:
    resultado = a.resultado(somar([{"satelite": "GOES-19", "frp": 50.0}]), ha_limiares=True)
    assert resultado["qtd_intensos"] == 0
