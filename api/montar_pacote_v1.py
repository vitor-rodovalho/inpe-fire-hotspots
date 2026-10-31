"""C5 (com a Frente D): leva o modelo real do BigQuery ML para a API.

  1. EXPORT MODEL de focos.modelo_foco_intenso para
     gs://<BUCKET>/modelos/foco_intenso/v1/ (sem custo). Pula se já exportado.
  2. Baixa do export só o que a API usa (model.bst e assets/) para
     dados/pacote_v1/ e salva o Booster de novo em JSON (model.json), para não
     depender do formato antigo do XGBoost 0.82.
  3. Grava satelites.json (de focos.satelites) e manifest.json.
  4. Gera model/paridade.jsonl: 50 focos do mês de teste lidos da Silver
     (40 completos, 5 com clima nulo e 5 com o bioma trocado por nulo), com a
     probabilidade dada pelo ML.PREDICT. Lê só PARIDADE_DIAS partições.
  5. Confere a paridade com o código da própria API (schemas -> features ->
     modelo), no model.bst e no model.json. Se um foco divergir, para aqui.
  6. Envia manifest.json, satelites.json e model.json para a pasta do export.

Custo: o EXPORT MODEL não cobra; as duas consultas leem alguns MB (bem menos de
US$ 0,01), com dry run antes e teto de bytes. Depois, a API passa a usar o
pacote com: bash api/subir_api.sh --modelo v1

Uso (a partir da raiz do repositório):
    pip install -r api/requirements-pacote.txt
    set -a; source config.env; set +a
    python3 api/montar_pacote_v1.py                 # passos 1 a 6
    python3 api/montar_pacote_v1.py --so-validar    # só o passo 5, sem GCP
    python3 api/montar_pacote_v1.py --refazer-export  # depois de treinar o modelo de novo
"""

import argparse
import datetime as dt
import json
import os
import sys
import warnings
from pathlib import Path

import xgboost as xgb

from app.features import preparar_variaveis
from app.modelo import ARQUIVO_MANIFESTO, ARQUIVO_SATELITES, PASTA_ASSETS, Modelo
from app.schemas import FocoEntrada

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")
BUCKET = os.environ.get("BUCKET", f"{PROJECT_ID}-data")
PASTA_MODELOS = os.environ.get("PASTA_MODELOS", "modelos/foco_intenso")
MES_TESTE = os.environ.get("MES_FIM", "2026-09")  # Último mês do histórico = mês de teste da Gold

MODELO_BQ = f"{PROJECT_ID}.{DATASET}.modelo_foco_intenso"
VERSAO_PASTA = "v1"
VERSAO_MODELO = "foco_intenso_v1"  # Mesmo apelido do Vertex AI Model Registry
LIMIAR_DECISAO = 0.5  # O do ML.PREDICT (predicted_foco_intenso) e da vw_previsoes
ARQUIVO_BST = "model.bst"
ARQUIVO_JSON = "model.json"

PARIDADE_PRIMEIRO_DIA = f"{MES_TESTE}-15"
PARIDADE_DIAS = 3
QTD_COMPLETOS, QTD_CLIMA_NULO, QTD_BIOMA_NULO = 40, 5, 5
TETO_BYTES = 1024**3  # 1 GiB: as consultas leem alguns MB
TOLERANCIA = 1e-6  # Booster contra ML.PREDICT

RAIZ_REPO = Path(__file__).resolve().parents[1]
PASTA_LOCAL = RAIZ_REPO / "dados" / "pacote_v1"
ARQUIVO_PARIDADE = RAIZ_REPO / "model" / "paridade.jsonl"
URI_PACOTE = f"gs://{BUCKET}/{PASTA_MODELOS}/{VERSAO_PASTA}"
CAMPOS_ENTRADA = ("satelite", "data_hora_gmt", "lat", "lon", "bioma",
                  "numero_dias_sem_chuva", "precipitacao", "risco_fogo")  # fmt: skip
# =============================================================================


def consultar(cliente, sql: str) -> list[dict]:
    """Consulta com dry run antes e maximum_bytes_billed."""
    from google.cloud import bigquery

    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > TETO_BYTES:
        sys.exit(f"ERRO: a consulta leria {estimativa / 1024**2:,.0f} MB, acima do teto de {TETO_BYTES / 1024**2:,.0f} MB.")
    print(f"  consulta vai ler {estimativa / 1024**2:,.1f} MB")
    config = bigquery.QueryJobConfig(maximum_bytes_billed=TETO_BYTES, labels={"frente": "d", "etapa": "c5"})
    return [dict(linha) for linha in cliente.query(sql, job_config=config).result()]


# =============================================================================
# Passos 1 a 4, no GCP
# =============================================================================
def exportar(cliente, bucket, refazer: bool) -> None:
    prefixo = f"{PASTA_MODELOS}/{VERSAO_PASTA}"
    if bucket.blob(f"{prefixo}/{ARQUIVO_BST}").exists() and not refazer:
        print(f"1. Export já existe em {URI_PACOTE}/, seguindo.")
    else:
        print(f"1. EXPORT MODEL {MODELO_BQ} -> {URI_PACOTE}/")
        cliente.query(f"EXPORT MODEL `{MODELO_BQ}` OPTIONS (URI = '{URI_PACOTE}/')").result()

    print(f"2. Baixando {ARQUIVO_BST} e {PASTA_ASSETS}/ para {PASTA_LOCAL}")
    nomes = [ARQUIVO_BST] + [b.name.removeprefix(f"{prefixo}/")
                             for b in bucket.list_blobs(prefix=f"{prefixo}/{PASTA_ASSETS}/")]  # fmt: skip
    for nome in nomes:
        destino = PASTA_LOCAL / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        bucket.blob(f"{prefixo}/{nome}").download_to_filename(destino)
        print(f"   {nome}")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*XGBoost < 1.0.0.*")
        xgb.Booster(model_file=str(PASTA_LOCAL / ARQUIVO_BST)).save_model(PASTA_LOCAL / ARQUIVO_JSON)
    print(f"   {ARQUIVO_JSON} (o mesmo Booster, salvo no formato atual)")


def gravar_referencias(cliente) -> None:
    print("3. satelites.json e manifest.json")
    satelites = {linha["satelite"]: linha["tipo_orbita"]
                 for linha in consultar(cliente, f"SELECT satelite, tipo_orbita FROM `{PROJECT_ID}.{DATASET}.satelites`")}  # fmt: skip
    (PASTA_LOCAL / ARQUIVO_SATELITES).write_text(
        json.dumps({"satelites": dict(sorted(satelites.items()))}, ensure_ascii=False, indent=2), encoding="utf-8")
    manifesto = {
        "versao_modelo": VERSAO_MODELO,
        "arquivo_modelo": ARQUIVO_JSON,
        "limiar_decisao": LIMIAR_DECISAO,
        "origem": f"EXPORT MODEL de {MODELO_BQ}",
        "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (PASTA_LOCAL / ARQUIVO_MANIFESTO).write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    print(f"   {len(satelites)} satélites; versão {VERSAO_MODELO}, limiar de decisão {LIMIAR_DECISAO}")


def gerar_paridade(cliente) -> None:
    """50 focos da Silver no mês de teste, com o ML.PREDICT, em model/paridade.jsonl."""
    print(f"4. Focos de paridade ({PARIDADE_DIAS} dias a partir de {PARIDADE_PRIMEIRO_DIA})")
    clima_nulo = "(numero_dias_sem_chuva IS NULL OR precipitacao IS NULL OR risco_fogo IS NULL)"
    grupos = [("completo", f"NOT {clima_nulo} AND bioma IS NOT NULL", "*", QTD_COMPLETOS),
              ("clima nulo", clima_nulo, "*", QTD_CLIMA_NULO),
              ("bioma nulo", f"NOT {clima_nulo}", "* REPLACE (CAST(NULL AS STRING) AS bioma)", QTD_BIOMA_NULO)]
    amostra = "\n  UNION ALL\n".join(
        f"(SELECT '{nome}' AS grupo, {selecao} FROM base WHERE {condicao} "
        f"ORDER BY FARM_FINGERPRINT(CONCAT('{nome}', id)) LIMIT {qtd})"
        for nome, condicao, selecao, qtd in grupos)
    # Só focos que a API aceita: as mesmas faixas de app/schemas.py
    sql = f"""
    WITH base AS (
      SELECT f.id, f.satelite, f.data_hora_gmt, f.lat, f.lon, f.bioma,
             f.numero_dias_sem_chuva, f.precipitacao, f.risco_fogo, f.frp,
             EXTRACT(HOUR FROM f.data_hora_gmt) AS hora, EXTRACT(MONTH FROM f.data_hora_gmt) AS mes,
             s.tipo_orbita
      FROM `{PROJECT_ID}.{DATASET}.silver_focos_historico` AS f
      JOIN `{PROJECT_ID}.{DATASET}.satelites` AS s USING (satelite)
      WHERE f.data_deteccao BETWEEN DATE '{PARIDADE_PRIMEIRO_DIA}'
                                AND DATE_ADD(DATE '{PARIDADE_PRIMEIRO_DIA}', INTERVAL {PARIDADE_DIAS - 1} DAY)
        AND f.lat BETWEEN -34 AND 5.5 AND f.lon BETWEEN -74.5 AND -28.5
        AND (f.risco_fogo IS NULL OR f.risco_fogo BETWEEN 0 AND 1)
        AND (f.numero_dias_sem_chuva IS NULL OR f.numero_dias_sem_chuva >= 0)
        AND (f.precipitacao IS NULL OR f.precipitacao >= 0)
        AND (f.bioma IS NULL OR f.bioma IN ('Amazônia', 'Caatinga', 'Cerrado', 'Mata Atlântica', 'Pampa', 'Pantanal'))
    )
    SELECT * EXCEPT (predicted_foco_intenso_probs, predicted_foco_intenso),
      predicted_foco_intenso AS intenso_bigquery,
      (SELECT p.prob FROM UNNEST(predicted_foco_intenso_probs) AS p WHERE p.label) AS prob_bigquery
    FROM ML.PREDICT(MODEL `{MODELO_BQ}`, (
  {amostra}
    ))
    ORDER BY grupo, id
    """
    linhas = consultar(cliente, sql)
    with ARQUIVO_PARIDADE.open("w", encoding="utf-8", newline="\n") as arquivo:
        for linha in linhas:
            foco = {campo: linha[campo] for campo in CAMPOS_ENTRADA}
            foco["data_hora_gmt"] = linha["data_hora_gmt"].strftime("%Y-%m-%dT%H:%M:%SZ")
            registro = {"grupo": linha["grupo"], "id": linha["id"], "frp": linha["frp"], "foco": foco,
                        "prob_bigquery": linha["prob_bigquery"], "intenso_bigquery": linha["intenso_bigquery"]}
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    contagem = {nome: sum(1 for linha in linhas if linha["grupo"] == nome) for nome, *_ in grupos}
    print(f"   {len(linhas)} focos em {ARQUIVO_PARIDADE.relative_to(RAIZ_REPO)}: {contagem}")
    for nome, _, _, qtd in grupos:
        if contagem[nome] < qtd:
            print(f"   Aviso: só {contagem[nome]} de {qtd} focos no grupo '{nome}' nesses dias.")


def publicar(bucket, arquivo_modelo: str) -> None:
    # model.bst e assets/ já estão lá, do EXPORT MODEL
    nomes = ([ARQUIVO_JSON] if arquivo_modelo == ARQUIVO_JSON else []) + [ARQUIVO_SATELITES, ARQUIVO_MANIFESTO]
    print(f"6. Enviando {', '.join(nomes)} para {URI_PACOTE}/")
    for nome in nomes:  # manifest por último: é ele que marca o pacote como pronto
        bucket.blob(f"{PASTA_MODELOS}/{VERSAO_PASTA}/{nome}").upload_from_filename(PASTA_LOCAL / nome)


# =============================================================================
# Passo 5, sem GCP
# =============================================================================
def ler_paridade(caminho: Path = ARQUIVO_PARIDADE) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def prever_local(modelo: Modelo, foco: dict) -> float:
    """O mesmo caminho do POST /predict, sem servidor."""
    entrada = FocoEntrada(**foco)
    return modelo.probabilidade(preparar_variaveis(entrada, modelo.tipo_orbita(entrada.satelite)))


def validar(pasta: Path = PASTA_LOCAL, paridade: Path = ARQUIVO_PARIDADE) -> str | None:
    """Confere os dois Boosters e devolve o que a API vai usar (None se nenhum passar).

    Prefere model.json; o model.bst do export fica como reserva, caso salvar de
    novo em JSON mude alguma probabilidade.
    """
    print("5. Paridade com o código da API")
    registros = ler_paridade(paridade)
    aprovados = []
    for arquivo in (ARQUIVO_JSON, ARQUIVO_BST):
        if not (pasta / arquivo).exists():
            continue
        modelo = _carregar_com(pasta, arquivo)
        diferencas = [abs(prever_local(modelo, r["foco"]) - r["prob_bigquery"]) for r in registros]
        iguais = sum(d <= TOLERANCIA for d in diferencas)
        print(f"   {arquivo}: {iguais} de {len(registros)} iguais ao ML.PREDICT (maior diferença {max(diferencas):.1e})")
        for grupo in sorted({r["grupo"] for r in registros}):
            itens = [d for d, r in zip(diferencas, registros) if r["grupo"] == grupo]
            print(f"     {grupo}: {sum(d <= TOLERANCIA for d in itens)} de {len(itens)}")
        if iguais == len(registros):
            aprovados.append(arquivo)

    if not aprovados:
        print("   NÃO PASSOU: o pacote não foi publicado.")
        return None
    escolhido = aprovados[0]
    manifesto = json.loads((pasta / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
    (pasta / ARQUIVO_MANIFESTO).write_text(json.dumps(manifesto | {"arquivo_modelo": escolhido}, indent=2),
                                           encoding="utf-8")
    print(f"   Passou. A API vai carregar {escolhido}.")
    return escolhido


def _carregar_com(pasta: Path, arquivo: str) -> Modelo:
    """Carrega o pacote com um Booster específico (model.bst do export ou model.json)."""
    modelo = Modelo.carregar(str(pasta))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*XGBoost < 1.0.0.*")
        booster = xgb.Booster(model_file=str(pasta / arquivo))
    return Modelo(modelo.versao, booster, modelo.variaveis, modelo.coluna_intenso,
                  modelo.limiar_decisao, modelo.satelites)  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--so-validar", action="store_true", help="Só confere a paridade, com os arquivos locais")
    parser.add_argument("--refazer-export", action="store_true",
                        help="Exporta de novo mesmo se já houver export (depois de treinar o modelo de novo)")
    args = parser.parse_args()

    if not args.so_validar:
        from google.cloud import bigquery, storage

        cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)
        bucket = storage.Client(project=PROJECT_ID).bucket(BUCKET)
        PASTA_LOCAL.mkdir(parents=True, exist_ok=True)
        exportar(cliente, bucket, args.refazer_export)
        gravar_referencias(cliente)
        gerar_paridade(cliente)

    escolhido = validar()
    if escolhido is None:
        sys.exit(1)
    if not args.so_validar:
        publicar(bucket, escolhido)
        print(f"\nPronto: pacote {VERSAO_MODELO} em {URI_PACOTE}/. Próximo passo: bash api/subir_api.sh --modelo v1")


if __name__ == "__main__":
    main()
