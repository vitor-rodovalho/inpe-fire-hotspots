"""Leitura das tabelas de referência (satelites e limiar_frp).

São tabelas pequenas e fixas durante a execução, então são lidas uma única vez,
quando o job sobe, e passadas ao pipeline como dicionários. Mudar uma delas
exige reiniciar o job (drain e deploy).

Para rodar sem BigQuery (testes, máquina local), use um JSON no formato de
references_example.json.
"""

import json
from typing import Any

# =============================================================================
# Constantes
# =============================================================================
TABELA_SATELITES = "satelites"
TABELA_LIMIARES = "limiar_frp"
# =============================================================================


def ler_do_bigquery(projeto, dataset) -> tuple[dict[Any, Any], dict[Any, float]]:
    """Devolve (satelites, limiares): {satelite: tipo_orbita}, {tipo_orbita: limiar}."""
    from google.cloud import bigquery  # importado aqui para os testes não dependerem dele

    cliente = bigquery.Client(project=projeto)
    satelites = {
        linha.satelite.strip(): linha.tipo_orbita
        for linha in cliente.query(
            f"SELECT satelite, tipo_orbita FROM `{projeto}.{dataset}.{TABELA_SATELITES}`"
        ).result()
    }
    limiares = {
        linha.tipo_orbita: float(linha.limiar)
        for linha in cliente.query(f"SELECT tipo_orbita, limiar FROM `{projeto}.{dataset}.{TABELA_LIMIARES}`").result()
    }
    return satelites, limiares


def ler_de_arquivo(caminho) -> tuple[dict[Any, Any], dict[Any, float]]:
    with open(caminho, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    return dict(dados["satelites"]), {k: float(v) for k, v in dados.get("limiares", {}).items()}
