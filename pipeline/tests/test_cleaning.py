"""Testes da validação e da limpeza (etapa B2 do plano)."""

import datetime as dt
import json
import os
from typing import Any

import pytest
from focos_stream import cleaning as t

INSTANTE_FIXO = dt.datetime(2026, 10, 16, 18, 0, 5, tzinfo=dt.timezone.utc)
CAMINHO_EXEMPLO = os.path.join(os.path.dirname(__file__), "data", "sample_hotspot.json")


@pytest.fixture
def foco() -> Any:
    with open(CAMINHO_EXEMPLO, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def motivo_da_rejeicao(foco) -> str:
    with pytest.raises(t.FocoInvalidoError) as erro:
        t.validar(foco)
    return str(erro.value)


# --- decodificação ---------------------------------------------------------


def test_decodifica_bytes_utf8(foco) -> None:
    assert t.decodificar(json.dumps(foco).encode("utf-8"))["bioma"] == "Amazônia"


@pytest.mark.parametrize(
    "corpo, motivo",
    [
        (b'{"id": "quebrado", ', "json_invalido"),
        (b"\xff\xfe", "json_invalido"),
        (b"[1, 2, 3]", "json_nao_e_objeto"),
    ],
)
def test_rejeita_corpo_que_nao_e_objeto_json(corpo, motivo):
    with pytest.raises(t.FocoInvalidoError, match=motivo):
        t.decodificar(corpo)


# --- validação -------------------------------------------------------------


def test_foco_completo_e_valido(foco) -> None:
    t.validar(foco)


def test_foco_sem_frp_e_valido(foco) -> None:
    foco["frp"] = ""
    t.validar(foco)


def test_foco_com_999_e_valido(foco) -> None:
    foco["frp"] = "-999"
    foco["risco_fogo"] = "-999"
    t.validar(foco)


@pytest.mark.parametrize("campo", ["id", "lat", "lon", "data_hora_gmt", "satelite", "estado"])
def test_rejeita_campo_obrigatorio_ausente(foco, campo) -> None:
    foco[campo] = "   "
    assert motivo_da_rejeicao(foco) == f"campo_obrigatorio_ausente:{campo}"


def test_rejeita_coordenada_fora_do_brasil(foco) -> None:
    foco["lat"], foco["lon"] = "40.7", "-74.0"
    assert motivo_da_rejeicao(foco) == "coordenada_fora_do_brasil"


def test_aceita_ilha_oceanica(foco) -> None:
    foco["lat"], foco["lon"] = "-3.85", "-32.42"  # Fernando de Noronha
    t.validar(foco)


def test_aceita_satelite_fora_da_tabela(foco) -> None:
    foco["satelite"] = "SATELITE-NOVO"  # a validação não consulta a tabela satelites
    t.validar(foco)
    assert t.limpar(foco, INSTANTE_FIXO)["satelite"] == "SATELITE-NOVO"


def test_apara_espacos_do_satelite(foco) -> None:
    foco["satelite"] = "  GOES-19 "
    t.validar(foco)
    assert t.limpar(foco, INSTANTE_FIXO)["satelite"] == "GOES-19"


def test_rejeita_numero_que_nao_e_numero(foco) -> None:
    foco["precipitacao"] = "abc"
    assert motivo_da_rejeicao(foco) == "numero_invalido:precipitacao"


def test_rejeita_data_invalida(foco) -> None:
    foco["data_hora_gmt"] = "30/09/2026"
    assert motivo_da_rejeicao(foco) == "data_hora_invalida"


def test_rejeita_risco_fogo_fora_da_faixa(foco) -> None:
    foco["risco_fogo"] = "1.5"
    assert motivo_da_rejeicao(foco) == "risco_fogo_fora_da_faixa"


# --- limpeza ---------------------------------------------------------------


def test_limpeza_converte_tipos_e_preenche_controle(foco) -> None:
    linha = t.limpar(foco, INSTANTE_FIXO)
    assert linha["lat"] == -9.51
    assert linha["numero_dias_sem_chuva"] == 21.0
    assert linha["municipio_id"] == 5100250
    assert linha["frp"] == 35.2
    assert linha["data_hora_gmt"] == "2026-09-30 18:40:00.000000 UTC"
    assert linha["data_deteccao"] == "2026-09-30"
    assert linha["origem"] == "streaming"
    assert linha["publicado_em"] == "2026-10-16 18:00:00.123000 UTC"
    assert linha["ingerido_em"] == "2026-10-16 18:00:05.000000 UTC"


def test_limpeza_tem_exatamente_as_colunas_da_silver(foco) -> None:
    colunas_silver = set(t.COLUNAS_INPE) | {"data_deteccao", "origem", "publicado_em", "ingerido_em"}
    assert set(t.limpar(foco, INSTANTE_FIXO)) == colunas_silver


@pytest.mark.parametrize("valor", ["", "  ", "-999", "-999.0", " -999 ", None])
def test_vazio_e_999_viram_nulo(foco, valor) -> None:
    foco["frp"] = valor
    foco["risco_fogo"] = valor
    linha = t.limpar(foco, INSTANTE_FIXO)
    assert linha["frp"] is None
    assert linha["risco_fogo"] is None


def test_frp_zero_nao_vira_nulo(foco) -> None:
    foco["frp"] = "0"
    assert t.limpar(foco, INSTANTE_FIXO)["frp"] == 0.0


def test_publicado_em_ausente_nao_rejeita(foco) -> None:
    del foco["publicado_em"]
    assert t.limpar(foco, INSTANTE_FIXO)["publicado_em"] is None


def test_aceita_valores_numericos_no_json(foco) -> None:
    foco["lat"], foco["frp"] = -9.51, 35.2
    t.validar(foco)
    assert t.limpar(foco, INSTANTE_FIXO)["frp"] == 35.2


# --- linha de erro ---------------------------------------------------------


def test_linha_de_erro_guarda_mensagem_e_motivo() -> None:
    linha = t.linha_de_erro(b'{"id": "x"', {"id": "x"}, "json_invalido", INSTANTE_FIXO)
    assert linha == {
        "mensagem_bruta": '{"id": "x"',
        "atributos": '{"id": "x"}',
        "motivo": "json_invalido",
        "recebido_em": "2026-10-16 18:00:05.000000 UTC",
    }
