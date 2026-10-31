import pytest
from pydantic import ValidationError

from app.features import preparar_variaveis
from app.schemas import FocoEntrada


@pytest.mark.parametrize("valor", [-999, "-999", " -999 ", "", "  ", None])
def test_vazio_e_menos_999_viram_nulo(foco, valor):
    foco.update(numero_dias_sem_chuva=valor, precipitacao=valor, risco_fogo=valor)
    entrada = FocoEntrada(**foco)
    assert entrada.numero_dias_sem_chuva is None
    assert entrada.precipitacao is None
    assert entrada.risco_fogo is None


@pytest.mark.parametrize("valor", [None, "", "  "])
def test_bioma_ausente_vira_nulo(foco, valor):
    foco["bioma"] = valor
    assert FocoEntrada(**foco).bioma is None
    del foco["bioma"]
    assert FocoEntrada(**foco).bioma is None


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("risco_fogo", 1.5),
        ("risco_fogo", -0.1),
        ("lat", 10.0),  # Ao norte do Brasil
        ("lon", -20.0),  # No meio do Atlântico
        ("numero_dias_sem_chuva", -1),
        ("bioma", "Savana"),
        ("satelite", "  "),
        ("data_hora_gmt", "ontem"),
    ],
)
def test_entrada_fora_da_faixa_e_recusada(foco, campo, valor):
    foco[campo] = valor
    with pytest.raises(ValidationError):
        FocoEntrada(**foco)


def test_hora_e_mes_sao_calculados_em_gmt(foco):
    # 30/09 22:30 em Brasília (-03:00) é 01/10 01:30 em GMT
    foco["data_hora_gmt"] = "2026-09-30T22:30:00-03:00"
    variaveis = preparar_variaveis(FocoEntrada(**foco), "polar")
    assert (variaveis["hora"], variaveis["mes"]) == (1, 10)


def test_horario_sem_fuso_e_lido_como_gmt(foco):
    foco["data_hora_gmt"] = "2026-10-14 18:42:00"  # Formato do CSV do INPE
    variaveis = preparar_variaveis(FocoEntrada(**foco), "polar")
    assert (variaveis["hora"], variaveis["mes"]) == (18, 10)


def test_variaveis_tem_os_nomes_da_gold(foco):
    variaveis = preparar_variaveis(FocoEntrada(**foco), "polar")
    assert set(variaveis) == {
        "lat", "lon", "hora", "mes", "tipo_orbita", "bioma",
        "numero_dias_sem_chuva", "precipitacao", "risco_fogo",
    }  # fmt: skip
