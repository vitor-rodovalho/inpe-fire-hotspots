"""Constantes e funções compartilhadas pelos scripts de ingestão.

- download_inpe.py: INPE -> Cloud Storage (alimenta o batch e guarda os diários)
- replay_pubsub.py: Cloud Storage -> Pub/Sub (alimenta o streaming)
"""

import csv
import io
import os
from typing import Any

# =============================================================================
# Constantes. Os valores vêm de config.env (carregado por ingestion/run.sh)
# Os padrões abaixo são os do contrato do projeto
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "")
BUCKET = os.environ.get("BUCKET", "")
TOPICO = os.environ.get("TOPICO", "focos-replay")

PASTA_RAW_MENSAL = os.environ.get("PASTA_RAW_MENSAL", "raw/mensal")
PASTA_RAW_DIARIO = os.environ.get("PASTA_RAW_DIARIO", "raw/diario")
PASTA_MANIFESTO = os.environ.get("PASTA_MANIFESTO", "raw/manifesto")

PADRAO_MENSAL = "focos_mensal_br_{periodo}"  # periodo = AAAAMM
PADRAO_DIARIO = "focos_diario_br_{periodo}"  # periodo = AAAAMMDD
ENCODING_CSV = "utf-8"
# =============================================================================


def nome_mensal(aaaamm) -> str:
    return PADRAO_MENSAL.format(periodo=aaaamm)


def nome_diario(aaaammdd) -> str:
    return PADRAO_DIARIO.format(periodo=aaaammdd)


def uri_diario(dia_iso) -> str:
    """'2026-09-30' -> gs://BUCKET/raw/diario/focos_diario_br_20260930.csv"""
    return f"gs://{BUCKET}/{PASTA_RAW_DIARIO}/{nome_diario(dia_iso.replace('-', ''))}.csv"


def ler_texto(caminho) -> str:
    """Conteúdo de um arquivo local ou gs://."""
    if caminho.startswith("gs://"):
        from google.cloud import storage

        bucket, _, nome = caminho[len("gs://") :].partition("/")
        return (
            storage.Client(project=PROJECT_ID or None).bucket(bucket).blob(nome).download_as_text(encoding=ENCODING_CSV)
        )
    with open(caminho, encoding=ENCODING_CSV) as arquivo:
        return arquivo.read()


def ler_csv(caminho) -> list[dict[str | Any, str | Any]]:
    """Linhas de um CSV do INPE como dicts, com os nomes das colunas aparados."""
    leitor = csv.DictReader(io.StringIO(ler_texto(caminho)))
    return [{chave.strip(): valor for chave, valor in linha.items()} for linha in leitor]
