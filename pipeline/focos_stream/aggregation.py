"""Agregação dos focos de uma janela de tempo e de um estado.

Funções puras, sem Apache Beam: o CombineFn em beam_transforms.py só chama
estas funções. Assim a conta pode ser testada com pytest.
"""

from typing import Any

# =============================================================================
# Constantes
# =============================================================================
CAMPOS_ACUMULADOR = ("qtd_focos", "qtd_sem_frp", "qtd_com_frp", "soma_frp", "qtd_intensos")
CASAS_DECIMAIS_FRP = 3
# =============================================================================


def acumulador_vazio() -> dict[str, Any]:
    return {"qtd_focos": 0, "qtd_sem_frp": 0, "qtd_com_frp": 0, "soma_frp": 0.0, "qtd_intensos": 0}


def adicionar(acumulador, foco, satelites, limiares) -> dict[str, Any]:
    """Soma um foco (linha da Silver) ao acumulador.

    satelites: dict satelite -> tipo_orbita
    limiares:  dict tipo_orbita -> limiar de FRP (pode estar vazio)
    """
    acumulador["qtd_focos"] += 1
    frp = foco.get("frp")
    if frp is None:
        acumulador["qtd_sem_frp"] += 1
        return acumulador
    acumulador["qtd_com_frp"] += 1
    acumulador["soma_frp"] += frp
    limiar = limiares.get(satelites.get(foco.get("satelite")))
    if limiar is not None and frp > limiar:
        acumulador["qtd_intensos"] += 1
    return acumulador


def mesclar(acumuladores) -> dict[str, Any]:
    total = acumulador_vazio()
    for acumulador in acumuladores:
        for campo in CAMPOS_ACUMULADOR:
            total[campo] += acumulador[campo]
    return total


def resultado(acumulador, ha_limiares) -> dict[str, Any]:
    """Valores finais de uma janela e estado.

    ha_limiares: False quando a tabela limiar_frp estava vazia ao subir o job;
    nesse caso qtd_intensos sai nulo, para não parecer que não houve intensos.
    """
    frp_medio = None
    if acumulador["qtd_com_frp"]:
        frp_medio = round(acumulador["soma_frp"] / acumulador["qtd_com_frp"], CASAS_DECIMAIS_FRP)
    return {
        "qtd_focos": acumulador["qtd_focos"],
        "qtd_sem_frp": acumulador["qtd_sem_frp"],
        "frp_medio": frp_medio,
        "qtd_intensos": acumulador["qtd_intensos"] if ha_limiares else None,
    }
