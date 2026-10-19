"""Carrega o pacote do modelo e calcula a probabilidade de um foco ser intenso.

O pacote é uma pasta (local ou no Cloud Storage) com três arquivos:

  manifest.json   Versão, arquivo do modelo, limiar de decisão e a lista
                  ordenada de variáveis, com as categorias das categóricas
  satelites.json  Satélite para tipo de órbita, no mesmo formato de
                  pipeline/references_example.json
  <modelo>        Booster do XGBoost (o nome vem do manifest)

A codificação (ordem das colunas, one-hot das categóricas) fica no manifest e
não no código. Assim, trocar o modelo provisório pelo exportado do BigQuery ML
muda o pacote, não a API.
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

# =============================================================================
# Constantes
# =============================================================================
ARQUIVO_MANIFESTO = "manifest.json"
ARQUIVO_SATELITES = "satelites.json"
PREFIXO_GCS = "gs://"
# =============================================================================

log = logging.getLogger(__name__)


def _baixar_do_gcs(uri: str, nomes: list[str], destino: Path) -> None:
    from google.cloud import storage  # importado aqui para os testes não dependerem dele

    bucket_nome, _, prefixo = uri.removeprefix(PREFIXO_GCS).partition("/")
    bucket = storage.Client().bucket(bucket_nome)
    for nome in nomes:
        caminho = f"{prefixo.rstrip('/')}/{nome}" if prefixo else nome
        bucket.blob(caminho).download_to_filename(destino / nome)
        log.info("Baixado %s%s/%s", PREFIXO_GCS, bucket_nome, caminho)


def _pasta_do_pacote(uri: str) -> Path:
    """Devolve a pasta local com o pacote, baixando do Cloud Storage se preciso."""
    if not uri.startswith(PREFIXO_GCS):
        return Path(uri)
    destino = Path(tempfile.mkdtemp(prefix="modelo_"))
    _baixar_do_gcs(uri, [ARQUIVO_MANIFESTO, ARQUIVO_SATELITES], destino)
    manifesto = json.loads((destino / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
    _baixar_do_gcs(uri, [manifesto["arquivo_modelo"]], destino)
    return destino


@dataclass(frozen=True)
class Modelo:
    versao: str
    booster: xgb.Booster
    variaveis: list[dict[str, Any]]  # [{"nome": ..., "tipo": "numerica" | "categorica", "categorias": [...]}]
    limiar_decisao: float
    satelites: dict[str, str]  # {satelite: tipo_orbita}

    @classmethod
    def carregar(cls, uri: str) -> "Modelo":
        pasta = _pasta_do_pacote(uri)
        manifesto = json.loads((pasta / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
        satelites = json.loads((pasta / ARQUIVO_SATELITES).read_text(encoding="utf-8"))["satelites"]

        booster = xgb.Booster()
        booster.load_model(pasta / manifesto["arquivo_modelo"])

        modelo = cls(
            versao=manifesto["versao_modelo"],
            booster=booster,
            variaveis=manifesto["variaveis"],
            limiar_decisao=float(manifesto["limiar_decisao"]),
            satelites={nome.strip(): orbita for nome, orbita in satelites.items()},
        )
        log.info("Modelo %s carregado de %s", modelo.versao, uri)
        return modelo

    def tipo_orbita(self, satelite: str) -> str | None:
        return self.satelites.get(satelite)

    def codificar(self, linha: dict[str, Any]) -> np.ndarray:
        """Variáveis nomeadas para o vetor na ordem do manifest. Nulo vira NaN."""
        valores: list[float] = []
        for variavel in self.variaveis:
            valor = linha[variavel["nome"]]
            if variavel["tipo"] == "categorica":
                valores.extend(1.0 if valor == categoria else 0.0 for categoria in variavel["categorias"])
            else:
                valores.append(np.nan if valor is None else float(valor))
        return np.array([valores], dtype=np.float32)

    def probabilidade(self, linha: dict[str, Any]) -> float:
        return float(self.booster.inplace_predict(self.codificar(linha))[0])
