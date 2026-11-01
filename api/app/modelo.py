"""Carrega o pacote do modelo e calcula a probabilidade de um foco ser intenso.

O pacote é a pasta do EXPORT MODEL do BigQuery ML (local ou no Cloud Storage),
com dois arquivos a mais, gravados por api/montar_pacote_v1.py:

  manifest.json                     Versão, arquivo do modelo e limiar de decisão
  satelites.json                    Satélite para tipo de órbita, no formato de
                                    pipeline/references_example.json
  model.json (ou model.bst)         Booster do XGBoost (o nome vem do manifest)
  assets/model_metadata.json        Do export: ordem das variáveis, média de cada
                                    numérica no treino e ordem das classes
  assets/<i>_categorical_label.txt  Do export: vocabulário da variável i

O vetor é montado como o ML.PREDICT o monta (model/README.md, seção C3), e não
como um XGBoost comum:

  - uma coluna por variável, na ordem de feature_names;
  - categórica: o índice do valor no vocabulário; nulo ou valor fora dele vira
    o índice 0 (_null_filler);
  - numérica: o valor; nulo vira a média do treino (o Booster nunca vê NaN).

A saída tem uma coluna por classe, na ordem de class_names; a probabilidade de
intenso é a coluna "true".
"""

import json
import logging
import tempfile
import warnings
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
PASTA_ASSETS = "assets"
ARQUIVO_METADADOS = f"{PASTA_ASSETS}/model_metadata.json"
SUFIXO_VOCABULARIO = "_categorical_label.txt"
CLASSE_INTENSO = "true"
PREFIXO_GCS = "gs://"
# =============================================================================

log = logging.getLogger(__name__)


def _baixar_do_gcs(uri: str, destino: Path) -> None:
    """Baixa só o que a API usa: manifest, satelites, o Booster e assets/.

    O export também traz um servidor de exemplo do Google e metadados do Vertex
    AI, que a API não usa e não precisa baixar.
    """
    from google.cloud import storage  # importado aqui para os testes não dependerem dele

    bucket_nome, _, prefixo = uri.removeprefix(PREFIXO_GCS).partition("/")
    prefixo = prefixo.rstrip("/")
    bucket = storage.Client().bucket(bucket_nome)

    def baixar(nome: str) -> None:
        arquivo = destino / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        bucket.blob(f"{prefixo}/{nome}").download_to_filename(arquivo)

    for nome in (ARQUIVO_MANIFESTO, ARQUIVO_SATELITES):
        baixar(nome)
    manifesto = json.loads((destino / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
    baixar(manifesto["arquivo_modelo"])
    for blob in bucket.list_blobs(prefix=f"{prefixo}/{PASTA_ASSETS}/"):
        baixar(blob.name.removeprefix(f"{prefixo}/"))
    log.info("Pacote baixado de %s", uri)


def _pasta_do_pacote(uri: str) -> Path:
    """Devolve a pasta local com o pacote, baixando do Cloud Storage se preciso."""
    if not uri.startswith(PREFIXO_GCS):
        return Path(uri)
    destino = Path(tempfile.mkdtemp(prefix="modelo_"))
    _baixar_do_gcs(uri, destino)
    return destino


def _ler_vocabularios(pasta: Path) -> dict[int, list[str]]:
    """{índice da variável: vocabulário}, de assets/<i>_categorical_label.txt."""
    return {
        int(arquivo.name.removesuffix(SUFIXO_VOCABULARIO)): arquivo.read_text(encoding="utf-8").splitlines()
        for arquivo in (pasta / PASTA_ASSETS).glob(f"*{SUFIXO_VOCABULARIO}")
    }


@dataclass(frozen=True)
class Variavel:
    nome: str
    vocabulario: list[str] | None = None  # Só nas categóricas
    media: float | None = None  # Só nas numéricas: substitui o nulo

    def codificar(self, valor: Any) -> float:
        if self.vocabulario is not None:
            return float(self.vocabulario.index(valor)) if valor in self.vocabulario else 0.0
        return self.media if valor is None else float(valor)


@dataclass(frozen=True)
class Modelo:
    versao: str
    booster: xgb.Booster
    variaveis: list[Variavel]
    coluna_intenso: int  # Posição da classe "true" na saída do Booster
    limiar_decisao: float
    satelites: dict[str, str]  # {satelite: tipo_orbita}

    @classmethod
    def carregar(cls, uri: str) -> "Modelo":
        pasta = _pasta_do_pacote(uri)
        manifesto = json.loads((pasta / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
        metadados = json.loads((pasta / ARQUIVO_METADADOS).read_text(encoding="utf-8"))
        satelites = json.loads((pasta / ARQUIVO_SATELITES).read_text(encoding="utf-8"))["satelites"]
        vocabularios = _ler_vocabularios(pasta)

        variaveis = [
            Variavel(nome, vocabulario=vocabularios[i])
            if i in vocabularios
            else Variavel(nome, media=float(metadados["features"][nome]["mean"]))
            for i, nome in enumerate(metadados["feature_names"])
        ]

        with warnings.catch_warnings():
            # O model.bst do export está no formato do XGBoost 0.82: carrega, mas avisa
            warnings.filterwarnings("ignore", message=".*XGBoost < 1.0.0.*")
            booster = xgb.Booster(model_file=str(pasta / manifesto["arquivo_modelo"]))

        modelo = cls(
            versao=manifesto["versao_modelo"],
            booster=booster,
            variaveis=variaveis,
            coluna_intenso=metadados["class_names"].index(CLASSE_INTENSO),
            limiar_decisao=float(manifesto["limiar_decisao"]),
            satelites={nome.strip(): orbita for nome, orbita in satelites.items()},
        )
        log.info("Modelo %s carregado de %s", modelo.versao, uri)
        return modelo

    def tipo_orbita(self, satelite: str) -> str | None:
        return self.satelites.get(satelite)

    def codificar(self, linha: dict[str, Any]) -> np.ndarray:
        """Variáveis nomeadas para o vetor que o Booster exportado espera."""
        return np.array([[variavel.codificar(linha[variavel.nome]) for variavel in self.variaveis]])

    def probabilidade(self, linha: dict[str, Any]) -> float:
        return float(self.booster.inplace_predict(self.codificar(linha))[0, self.coluna_intenso])
