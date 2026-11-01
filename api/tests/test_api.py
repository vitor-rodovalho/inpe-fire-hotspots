from app.main import CABECALHO_TEMPO


def test_health_informa_a_versao(cliente):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "versao_modelo": "foco_intenso_provisorio_v0"}


def test_predict_segue_o_contrato(cliente, foco):
    resposta = cliente.post("/predict", json=foco)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"probabilidade_intenso", "intenso", "versao_modelo"}
    assert 0 <= corpo["probabilidade_intenso"] <= 1
    assert corpo["intenso"] == (corpo["probabilidade_intenso"] >= 0.5)
    assert float(resposta.headers[CABECALHO_TEMPO]) >= 0


def test_linha_da_silver_e_aceita_como_esta(cliente, foco):
    """Campos a mais (id, frp, municipio...) são ignorados; o FRP não muda a resposta."""
    linha_silver = foco | {"id": "abc", "frp": 999.0, "municipio": "ALTA FLORESTA", "origem": "streaming"}
    assert cliente.post("/predict", json=linha_silver).json() == cliente.post("/predict", json=foco).json()


def test_foco_sem_dados_de_clima(cliente, foco):
    foco.update(numero_dias_sem_chuva=-999, precipitacao=None, risco_fogo="")
    assert cliente.post("/predict", json=foco).status_code == 200


def test_foco_sem_bioma(cliente, foco):
    del foco["bioma"]
    assert cliente.post("/predict", json=foco).status_code == 200


def test_condicoes_secas_dao_probabilidade_maior(cliente, foco):
    seco = foco | {"numero_dias_sem_chuva": 50, "precipitacao": 0.0, "risco_fogo": 1.0}
    umido = foco | {"numero_dias_sem_chuva": 0, "precipitacao": 10.0, "risco_fogo": 0.05}
    p_seco = cliente.post("/predict", json=seco).json()["probabilidade_intenso"]
    p_umido = cliente.post("/predict", json=umido).json()["probabilidade_intenso"]
    assert p_seco > p_umido


def test_satelite_desconhecido_da_422(cliente, foco):
    resposta = cliente.post("/predict", json=foco | {"satelite": "SPUTNIK-1"})
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["loc"] == ["body", "satelite"]


def test_risco_fora_da_faixa_da_422(cliente, foco):
    resposta = cliente.post("/predict", json=foco | {"risco_fogo": 1.5})
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["loc"] == ["body", "risco_fogo"]


def test_campo_obrigatorio_ausente_da_422(cliente, foco):
    del foco["lat"]
    assert cliente.post("/predict", json=foco).status_code == 422
