"""C3. Exportação de brinquedo: o boosted tree do BigQuery ML fora do BigQuery.

Antes do modelo real (C4), prova que o modelo exportado do BigQuery ML dá, em
Python, a mesma resposta que o ML.PREDICT, e descobre o que a API precisa para
isso (plano, Frente C):

  1. treina um boosted tree pequeno na Gold de treino (um foco em cada
     UM_EM_CADA do treino, ~10 mil), com as opções do plano e os
     hiperparâmetros da C2;
  2. exporta com EXPORT MODEL, baixa os arquivos para dados/c3_brinquedo/ e
     guarda o ML.PREDICT de focos do mês de teste, incluindo focos com bioma
     ou clima nulos, que é onde as codificações costumam divergir;
  3. carrega o Booster no xgboost fixado pela API (api/requirements.txt da
     branch da Frente D), lê os metadados exportados (ordem das variáveis,
     codificação das categóricas, tratamento dos nulos) e compara, foco a foco,
     a probabilidade do Booster com a do ML.PREDICT;
  4. grava em model/README.md, na seção da C3, a versão, o resultado e o passo
     a passo da preparação das variáveis para a Frente D.

O treino roda no Vertex AI e é cobrado na tarifa de consulta (US$ 6,25 por
TiB), com o tempo de máquina convertido em bytes: ~20 minutos e ~US$ 0,33 no
teste de 29/10, quase sem depender do número de focos. O job tem teto de bytes
e é cancelado depois de LIMITE_MINUTOS. No fim, o modelo de brinquedo e o export
no bucket são apagados (--manter para deixar).

Uso (a partir da raiz do repositório):
    pip install -r model/requirements.txt
    git fetch origin frente-d/api
    set -a; source config.env; set +a
    python3 model/exportacao_brinquedo.py               # treina, exporta e valida (GCP, ~US$ 0,35)
    python3 model/exportacao_brinquedo.py --so-validar  # só os passos 3 e 4, com os arquivos já baixados
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

import sinal_modelo

# =============================================================================
# Constantes. Os valores vêm de config.env; os padrões são os do contrato
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")
BUCKET = os.environ.get("BUCKET", f"{PROJECT_ID}-data")
TABELA_GOLD = f"{PROJECT_ID}.{DATASET}.gold_treino"
MODELO = f"{PROJECT_ID}.{DATASET}.foco_intenso_brinquedo"
PREFIXO_EXPORT = "modelos/foco_intenso/brinquedo"
ROTULO = "foco_intenso"

UM_EM_CADA = 253                   # ~10 mil focos de treino: o custo depende do tempo, não do volume
QTD_PARIDADE = 400                 # Focos de teste sem nenhum nulo...
QTD_PARIDADE_NULOS = 100           # ... e com bioma ou clima nulos
LIMITE_GB_CONSULTA = 2
TETO_GIB_TREINO = 100              # US$ 0,61 na tarifa de US$ 6,25 por TiB
LIMITE_MINUTOS = 60
INTERVALO_SEGUNDOS = 30
TARIFA_TIB = 6.25
TOLERANCIA = 1e-6

REF_API = "origin/frente-d/api"    # Branch da Frente D com a API
VERSAO_XGBOOST_PADRAO = "2.1.3"    # Se a branch não estiver disponível

P = sinal_modelo.PARAMETROS_XGB    # Os mesmos da C2
OPCOES_MODELO = f"""
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['{ROTULO}'],
  auto_class_weights = TRUE,
  data_split_method = 'NO_SPLIT',
  early_stop = FALSE,
  max_iterations = {P['n_estimators']},
  max_tree_depth = {P['max_depth']},
  learn_rate = {P['learning_rate']},
  subsample = {P['subsample']},
  colsample_bytree = {P['colsample_bytree']},
  tree_method = 'HIST'
"""

RAIZ_REPO = Path(__file__).resolve().parents[1]
PASTA = RAIZ_REPO / "dados" / "c3_brinquedo"
PASTA_EXPORT = PASTA / "export"
ARQUIVO_TREINO = PASTA / "treino.json"
ARQUIVO_PREDICT = PASTA / "predict.jsonl"

CAMINHO_README = RAIZ_REPO / "model" / "README.md"
MARCA_INICIO = "<!-- C3: início (gerado por model/exportacao_brinquedo.py) -->"
MARCA_FIM = "<!-- C3: fim -->"
# =============================================================================


def gib(valor) -> float:
    return (valor or 0) / 1024**3


def consultar(cliente, sql) -> pd.DataFrame:
    """Consulta com dry run antes e maximum_bytes_billed."""
    from google.cloud import bigquery

    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > limite:
        raise RuntimeError(f"Consulta leria mais de {LIMITE_GB_CONSULTA} GB.")
    print(f"  consulta vai ler {estimativa / 1024**2:,.1f} MB")
    return cliente.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=limite)).to_dataframe()


# =============================================================================
# Passos 1 e 2, no GCP
# =============================================================================
def treinar(cliente) -> dict:
    """CREATE MODEL até o fim, com teto de bytes e de tempo."""
    from google.cloud import bigquery

    filtro = f"conjunto = 'treino' AND MOD(ABS(FARM_FINGERPRINT(TO_JSON_STRING(g))), {UM_EM_CADA}) = 0"
    contagem = consultar(cliente, f"SELECT COUNT(*) AS focos, COUNTIF({ROTULO}) AS positivos "
                                  f"FROM `{TABELA_GOLD}` AS g WHERE {filtro}")
    print(f"Amostra: {int(contagem.focos[0]):,} focos de treino, {int(contagem.positivos[0]):,} intensos")

    sql = f"""
    CREATE OR REPLACE MODEL `{MODELO}`
    OPTIONS ({OPCOES_MODELO})
    AS
    SELECT * EXCEPT (conjunto) FROM `{TABELA_GOLD}` AS g WHERE {filtro}
    """
    config = bigquery.QueryJobConfig(maximum_bytes_billed=int(TETO_GIB_TREINO * 1024**3),
                                     labels={"frente": "c", "etapa": "c3"})
    job = cliente.query(sql, job_config=config)
    inicio = time.monotonic()
    print(f"CREATE MODEL {job.job_id}: teto {TETO_GIB_TREINO} GiB, cancela em {LIMITE_MINUTOS} min")
    while not job.done(reload=True):
        minutos = (time.monotonic() - inicio) / 60
        if minutos > LIMITE_MINUTOS:
            job.cancel()
            raise RuntimeError(f"CREATE MODEL cancelado depois de {minutos:.0f} min; confira o faturamento.")
        print(f"  {minutos:5.1f} min, {job.state}", flush=True)
        time.sleep(INTERVALO_SEGUNDOS)
    if job.error_result:
        raise RuntimeError(f"CREATE MODEL falhou: {job.error_result}")

    treino = {
        "modelo": MODELO, "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "focos": int(contagem.focos[0]), "positivos": int(contagem.positivos[0]), "job_id": job.job_id,
        "segundos": (job.ended - job.started).total_seconds(), "bytes_faturados": job.total_bytes_billed,
        "iteracoes": P["n_estimators"],
    }
    print(f"Fim: {treino['segundos']:.0f} s, {gib(job.total_bytes_billed):.1f} GiB faturados "
          f"(US$ {gib(job.total_bytes_billed) / 1024 * TARIFA_TIB:.2f})")
    return treino


def exportar(cliente, manter) -> None:
    """EXPORT MODEL, download dos arquivos e ML.PREDICT de focos de teste, com e sem nulos."""
    from google.cloud import storage

    uri = f"gs://{BUCKET}/{PREFIXO_EXPORT}/"
    cliente.query(f"EXPORT MODEL `{MODELO}` OPTIONS (URI = '{uri}')").result()
    blobs = list(storage.Client(project=PROJECT_ID).list_blobs(BUCKET, prefix=PREFIXO_EXPORT + "/"))
    for blob in blobs:
        destino = PASTA_EXPORT / blob.name.removeprefix(PREFIXO_EXPORT + "/")
        destino.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(destino)
    print(f"Export: {len(blobs)} arquivos de {uri} em {PASTA_EXPORT}")

    tem_nulo = ("bioma IS NULL OR numero_dias_sem_chuva IS NULL OR precipitacao IS NULL "
                "OR risco_fogo IS NULL")
    amostra = f"""
      (SELECT * EXCEPT (conjunto) FROM `{TABELA_GOLD}` AS g
       WHERE conjunto = 'teste' AND NOT ({tem_nulo})
       ORDER BY FARM_FINGERPRINT(TO_JSON_STRING(g)) LIMIT {QTD_PARIDADE})
      UNION ALL
      (SELECT * EXCEPT (conjunto) FROM `{TABELA_GOLD}` AS g
       WHERE conjunto = 'teste' AND ({tem_nulo})
       ORDER BY FARM_FINGERPRINT(TO_JSON_STRING(g)) LIMIT {QTD_PARIDADE_NULOS})"""
    previsto = consultar(cliente, f"""
        SELECT * EXCEPT (predicted_{ROTULO}_probs),
          (SELECT p.prob FROM UNNEST(predicted_{ROTULO}_probs) AS p WHERE p.label) AS prob
        FROM ML.PREDICT(MODEL `{MODELO}`, ({amostra}))""")
    previsto.to_json(ARQUIVO_PREDICT, orient="records", lines=True, force_ascii=False)
    print(f"ML.PREDICT: {len(previsto)} focos de teste em {ARQUIVO_PREDICT}")

    if not manter:
        cliente.delete_model(MODELO)
        for blob in blobs:
            blob.delete()
        print(f"Modelo de brinquedo e export no bucket apagados (os arquivos ficam em {PASTA_EXPORT})")


# =============================================================================
# Passos 3 e 4, sem GCP
# =============================================================================
def versao_xgboost_api() -> str:
    """Versão do xgboost fixada em api/requirements.txt na branch da Frente D."""
    try:
        requisitos = subprocess.run(["git", "-C", str(RAIZ_REPO), "show", f"{REF_API}:api/requirements.txt"],
                                    check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return VERSAO_XGBOOST_PADRAO
    achado = re.search(r"^xgboost(?:-cpu)?==([\w.]+)", requisitos, re.MULTILINE)
    return achado.group(1) if achado else VERSAO_XGBOOST_PADRAO


def ler_export(pasta) -> tuple[dict, dict[int, list[str]], xgb.Booster, list[str]]:
    """Metadados, vocabulários das categóricas (pelo índice da variável), Booster e avisos da carga."""
    metadados = json.loads((pasta / "assets" / "model_metadata.json").read_text(encoding="utf-8"))
    vocabularios = {int(arquivo.name.split("_")[0]): arquivo.read_text(encoding="utf-8").splitlines()
                    for arquivo in (pasta / "assets").glob("*_categorical_label.txt")}
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        booster = xgb.Booster(model_file=str(pasta / "model.bst"))
    return metadados, vocabularios, booster, [str(aviso.message) for aviso in avisos]


def matriz_export(focos, metadados, vocabularios) -> np.ndarray:
    """O vetor que o Booster exportado espera, como o BigQuery ML o monta.

    Ordem: feature_names de model_metadata.json. Categórica: índice do valor no
    vocabulário assets/<i>_categorical_label.txt, com o nulo em _null_filler
    (índice 0). Numérica: o valor, com o nulo trocado pela média do treino
    gravada nos metadados (o Booster exportado nunca recebe NaN).
    """
    colunas = []
    for i, nome in enumerate(metadados["feature_names"]):
        if i in vocabularios:
            vocab = vocabularios[i]
            colunas.append(focos[nome].map(lambda valor: float(vocab.index(valor)) if valor in vocab else 0.0))
        else:
            media = metadados["features"][nome]["mean"]
            colunas.append(pd.to_numeric(focos[nome]).astype(float).fillna(media))
    return np.column_stack(colunas).astype(float)


def validar() -> dict:
    metadados, vocabularios, booster, avisos = ler_export(PASTA_EXPORT)
    previsto = pd.read_json(ARQUIVO_PREDICT, lines=True)
    saida = booster.predict(xgb.DMatrix(matriz_export(previsto, metadados, vocabularios)))
    prob = saida[:, metadados["class_names"].index("true")]
    iguais = np.abs(prob - previsto["prob"].to_numpy()) <= TOLERANCIA

    numericas = [n for n in metadados["feature_names"] if n not in
                 {metadados["feature_names"][i] for i in vocabularios}]
    grupos = {
        "sem nulos": previsto[numericas + ["bioma"]].notna().all(axis=1),
        "bioma nulo": previsto["bioma"].isna(),
        "clima nulo": previsto[numericas].isna().any(axis=1),
    }
    config = json.loads(booster.save_config())
    return {
        "metadados": metadados, "vocabularios": vocabularios, "avisos": avisos,
        "xgboost_local": xgb.__version__, "xgboost_api": versao_xgboost_api(),
        "objetivo": config["learner"]["objective"]["name"],
        "arvores": booster.num_boosted_rounds(), "colunas": booster.num_features(),
        "arquivos": sorted(str(a.relative_to(PASTA_EXPORT)) for a in PASTA_EXPORT.rglob("*") if a.is_file()),
        "focos": len(previsto), "iguais": int(iguais.sum()),
        "max_diferenca": float(np.abs(prob - previsto["prob"].to_numpy()).max()),
        "grupos": {nome: (int(m.sum()), int(iguais[m.to_numpy()].sum())) for nome, m in grupos.items()},
    }


def texto_readme(r, treino) -> str:
    metadados, vocabularios = r["metadados"], r["vocabularios"]
    passou = r["iguais"] == r["focos"] and r["xgboost_local"] == r["xgboost_api"]
    custo = gib(treino["bytes_faturados"]) / 1024 * TARIFA_TIB
    grupos = "; ".join(f"{nome}: {iguais} de {total}" for nome, (total, iguais) in r["grupos"].items())
    total_bioma_nulo, _ = r["grupos"]["bioma nulo"]
    aviso_formato = next((a for a in r["avisos"] if "XGBoost < 1.0.0" in a), None)

    variaveis = []
    for i, nome in enumerate(metadados["feature_names"]):
        if i in vocabularios:
            lista = ", ".join(f"{indice} = `{valor}`" for indice, valor in enumerate(vocabularios[i]))
            variaveis.append(f"   {i}. `{nome}`: índice no vocabulário ({lista})")
        else:
            variaveis.append(f"   {i}. `{nome}`: o valor; nulo vira {metadados['features'][nome]['mean']!r}")

    return "\n".join([
        MARCA_INICIO,
        "## C3. Exportação de brinquedo",
        "",
        f"Gerado por `model/exportacao_brinquedo.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC. "
        f"O boosted tree do BigQuery ML foi treinado com {sinal_modelo.milhar(treino['focos'])} focos de treino "
        f"da Gold ({sinal_modelo.milhar(treino['positivos'])} intensos), com as opções do plano e os "
        f"hiperparâmetros da C2 ({treino['iteracoes']} iterações), exportado com `EXPORT MODEL` e carregado "
        f"em Python. O treino levou {treino['segundos'] / 60:.0f} minutos e faturou "
        f"{gib(treino['bytes_faturados']):.1f} GiB (US$ {custo:.2f}).",
        "",
        "### Resultado",
        "",
        f"- **Versão do XGBoost:** a API fixa `xgboost-cpu=={r['xgboost_api']}`; o Booster exportado carrega "
        f"no xgboost {r['xgboost_local']} ({r['arvores']} árvores, {r['colunas']} colunas, objetivo "
        f"`{r['objetivo']}`)."
        + (" O arquivo está no formato binário anterior ao XGBoost 1.0, e a carga avisa: \"consider "
           "saving it again for improved compatibility\". Na C5, o pacote v1 leva também o Booster "
           "salvo de novo em JSON, para não depender desse formato." if aviso_formato else ""),
        f"- **Arquivos do export:** {', '.join(f'`{a}`' for a in r['arquivos'])}.",
        f"- **Paridade:** {r['iguais']} de {r['focos']} probabilidades do Booster iguais às do `ML.PREDICT` "
        f"(maior diferença {r['max_diferenca']:.1e}). Por grupo: {grupos}. "
        f"{'Passou.' if passou else '**Não passou.**'}",
        "- **Bioma nulo:** " + ("confirmado: o BigQuery ML trata o nulo como a categoria `_null_filler`."
                                if total_bioma_nulo else
                                "a amostra não teve focos sem bioma, então a regra do `_null_filler` vem do "
                                "`predictor.py` do export e ainda precisa ser conferida (rode o script de novo "
                                "ou confira na C5)."),
        "",
        "### Passo a passo da preparação das variáveis (para a Frente D)",
        "",
        "É o que o `ML.PREDICT` faz e o que a API precisa reproduzir para dar a mesma probabilidade:",
        "",
        "1. `hora` = `EXTRACT(HOUR FROM data_hora_gmt)` e `mes` = `EXTRACT(MONTH FROM data_hora_gmt)`, em UTC, "
        "como na Gold.",
        "2. `tipo_orbita` vem de `focos.satelites`.",
        "3. O vetor tem as variáveis na ordem de `feature_names` em `assets/model_metadata.json`, uma coluna "
        "por variável (as categóricas não viram one-hot):",
        "",
        *variaveis,
        "",
        "4. Carregar com `xgb.Booster(model_file=\"model.bst\")` e chamar `predict` sem valores ausentes. A saída "
        f"tem uma coluna por classe, na ordem de `class_names` ({metadados['class_names']}): a probabilidade "
        "de intenso é a coluna de `\"true\"`.",
        "",
        "O `predictor.py` que vem no export (`xgboost_predictor-0.1.tar.gz`) não serve à API como está: ele "
        "quebra com numérica nula (`float(None)`), enquanto o BigQuery ML usa a média, e deixa a categoria "
        "nula como ausente, enquanto o vocabulário do export reserva o índice 0 (`_null_filler`) para ela.",
        "",
        "### Para a Frente D",
        "",
        "- O modelo real (C4) é exportado igual, em `gs://<BUCKET>/modelos/foco_intenso/v1/` (C5), com os "
        "mesmos arquivos. O `modelo.py` da API, que hoje monta one-hot pelo `manifest.json` do modelo "
        "provisório, precisa montar o vetor como acima, lendo os vocabulários e as médias do próprio export.",
        "- O limiar de decisão de `intenso` sai da C4. Com `auto_class_weights`, a probabilidade não é "
        "calibrada, e 0,5 marca intensos demais.",
        MARCA_FIM,
    ])


def atualizar_readme(texto) -> None:
    atual = CAMINHO_README.read_text(encoding="utf-8")
    padrao = re.compile(r"<!-- C3: início .*?<!-- C3: fim -->", re.DOTALL)
    novo = padrao.sub(lambda _m: texto, atual) if padrao.search(atual) else atual.rstrip("\n") + "\n\n" + texto
    CAMINHO_README.write_text(novo.rstrip("\n") + "\n", encoding="utf-8")
    print(f"\nResultado gravado em {CAMINHO_README}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--so-validar", action="store_true", help="Usa os arquivos já baixados, sem GCP")
    parser.add_argument("--manter", action="store_true", help="Não apaga o modelo nem o export no bucket")
    parser.add_argument("--sem-readme", action="store_true", help="Só imprime o resultado")
    args = parser.parse_args()

    if not args.so_validar:
        from google.cloud import bigquery

        cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)
        PASTA.mkdir(parents=True, exist_ok=True)
        treino = treinar(cliente)
        ARQUIVO_TREINO.write_text(json.dumps(treino, indent=2), encoding="utf-8")
        exportar(cliente, args.manter)

    treino = json.loads(ARQUIVO_TREINO.read_text(encoding="utf-8"))
    texto = texto_readme(validar(), treino)
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
