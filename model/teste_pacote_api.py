"""C3. Teste do pacote do modelo contra a API (a "exportação de brinquedo" do plano).

O modelo real vai ser um XGBoost treinado aqui, fora do BigQuery ML (a reserva
do plano; ver "Custos no GCP" no README). Esta etapa prova, antes do modelo
real, que o pacote que a Frente C gera é lido pela API da Frente D e dá a mesma
resposta:

  1. treina um XGBoost pequeno com 500 focos reais da Gold de treino
     (focos.gold_treino, A7), as "poucas centenas de linhas" do plano; com
     --sintetico, usa 500 focos inventados e nada roda no GCP;
  2. grava o pacote (model/pacote.py) em dados/pacote_teste/;
  3. copia o código da API da branch da Frente D (git show, só leitura) para
     dados/api_frente_d/ e carrega o pacote com a classe Modelo de lá;
  4. compara, foco a foco, o vetor montado pela API com o do treino e a
     probabilidade da API com a do Booster, e conta os valores de bioma e
     tipo_orbita que não estão no manifest (a API os codificaria como zeros);
  5. grava a versão do XGBoost e o passo a passo da preparação das variáveis em
     model/README.md, na seção da C3.

Uso (a partir da raiz do repositório, com o xgboost da API instalado):
    pip install -r model/requirements.txt
    git fetch origin frente-d/api
    set -a; source config.env; set +a
    python3 model/teste_pacote_api.py               # 500 focos da Gold (dry run antes)
    python3 model/teste_pacote_api.py --sintetico   # sem GCP, custo zero
"""

import argparse
import datetime as dt
import importlib
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import xgboost as xgb

import pacote

# =============================================================================
# Constantes
# =============================================================================
PROJECT_ID = os.environ.get("PROJECT_ID", "inpe-fire-hotspots")
REGIAO = os.environ.get("REGIAO", "us-central1")
DATASET = os.environ.get("DATASET", "focos")
TABELA_GOLD = f"{PROJECT_ID}.{DATASET}.gold_treino"
LIMITE_GB_CONSULTA = 1

REF_API = "origin/frente-d/api"            # Branch da Frente D com a API
ARQUIVOS_API = ["api/app/__init__.py", "api/app/modelo.py", "api/requirements.txt"]
PASTA_DADOS = pacote.RAIZ_REPO / "dados"
PASTA_PACOTE = PASTA_DADOS / "pacote_teste"
PASTA_API = PASTA_DADOS / "api_frente_d"
VERSAO = "foco_intenso_teste_v0"

QTD_FOCOS = 500
QTD_ARVORES = 20
SEMENTE = 42
TOLERANCIA = 1e-6                           # Mesma biblioteca nas duas pontas: devem ser iguais

CAMINHO_README = pacote.RAIZ_REPO / "model" / "README.md"
MARCA_INICIO = "<!-- C3: início (gerado por model/teste_pacote_api.py) -->"
MARCA_FIM = "<!-- C3: fim -->"
# =============================================================================


def focos_da_gold() -> pd.DataFrame:
    """500 focos de treino da Gold, sempre os mesmos (ordem por hash da linha), com dry run antes."""
    from google.cloud import bigquery

    sql = f"""
    SELECT * EXCEPT (conjunto)
    FROM `{TABELA_GOLD}` AS g
    WHERE conjunto = 'treino'
    ORDER BY FARM_FINGERPRINT(TO_JSON_STRING(g))
    LIMIT {QTD_FOCOS}
    """
    cliente = bigquery.Client(project=PROJECT_ID, location=REGIAO)
    limite = int(LIMITE_GB_CONSULTA * 1024**3)
    estimativa = cliente.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    if estimativa > limite:
        raise RuntimeError(f"Consulta leria mais de {LIMITE_GB_CONSULTA} GB.")
    print(f"Consulta vai ler {estimativa / 1024**2:,.1f} MB da Gold de treino")
    focos = cliente.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=limite)).to_dataframe()
    focos["foco_intenso"] = focos["foco_intenso"].astype(int)
    return focos


def focos_sinteticos(rng) -> pd.DataFrame:
    """Focos com as colunas e as categorias da Gold, incluindo nulos como nos dados reais."""
    n = QTD_FOCOS
    focos = pd.DataFrame({
        "lat": rng.uniform(-33, 5, n),
        "lon": rng.uniform(-73, -35, n),
        "hora": rng.integers(0, 24, n),
        "mes": rng.integers(1, 13, n),
        "tipo_orbita": rng.choice(pacote.ORBITAS, n),
        "bioma": rng.choice(pacote.BIOMAS + [None], n),
        "numero_dias_sem_chuva": rng.integers(0, 60, n).astype(float),
        "precipitacao": rng.exponential(2.0, n),
        "risco_fogo": rng.uniform(0, 1, n),
    })
    for coluna, fracao in (("numero_dias_sem_chuva", 0.03), ("precipitacao", 0.02), ("risco_fogo", 0.025)):
        focos.loc[rng.random(n) < fracao, coluna] = np.nan   # Parcelas parecidas com as do perfil (A1)
    logit = -2.5 + 2.5 * focos["risco_fogo"].fillna(0.5) + 0.03 * focos["numero_dias_sem_chuva"].fillna(10)
    focos["foco_intenso"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return focos


def copiar_api() -> str:
    """Copia os arquivos da API da branch da Frente D e devolve a versão do xgboost fixada nela."""
    if PASTA_API.exists():
        shutil.rmtree(PASTA_API)
    for caminho in ARQUIVOS_API:
        conteudo = subprocess.run(["git", "-C", str(pacote.RAIZ_REPO), "show", f"{REF_API}:{caminho}"],
                                  check=True, capture_output=True).stdout
        destino = PASTA_API / caminho.removeprefix("api/")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
    requisitos = (PASTA_API / "requirements.txt").read_text(encoding="utf-8")
    achado = re.search(r"^xgboost(?:-cpu)?==([\w.]+)", requisitos, re.MULTILINE)
    return achado.group(1) if achado else "não fixada"


def carregar_modelo_da_api():
    sys.path.insert(0, str(PASTA_API))
    modulo = importlib.import_module("app.modelo")
    return modulo.Modelo.carregar(str(PASTA_PACOTE))


def linha_da_api(foco) -> dict:
    """Linha do DataFrame como a API recebe: nulos como None."""
    return {chave: (None if not isinstance(valor, str) and pd.isna(valor) else valor)
            for chave, valor in foco.items() if chave != "foco_intenso"}


def fora_do_manifest(focos) -> dict[str, list[str]]:
    """Valores não nulos de cada categórica que não estão na lista do manifest."""
    return {v["nome"]: sorted(set(focos[v["nome"]].dropna()) - set(v["categorias"]))
            for v in pacote.VARIAVEIS if v["tipo"] == "categorica"}


def validar(focos, booster, modelo_api) -> dict:
    matriz = pacote.montar_matriz(focos)
    prob_treino = booster.inplace_predict(matriz)
    vetores_iguais, diferencas = 0, []
    for i, foco in enumerate(focos.to_dict("records")):
        linha = linha_da_api(foco)
        if np.array_equal(modelo_api.codificar(linha)[0], matriz[i], equal_nan=True):
            vetores_iguais += 1
        diferencas.append(abs(modelo_api.probabilidade(linha) - float(prob_treino[i])))
    return {
        "focos": len(focos),
        "colunas": matriz.shape[1],
        "vetores_iguais": vetores_iguais,
        "max_diferenca": max(diferencas),
        "iguais": sum(d <= TOLERANCIA for d in diferencas),
        "versao_carregada": modelo_api.versao,
        "fora_do_manifest": fora_do_manifest(focos),
        "sem_bioma": int(focos["bioma"].isna().sum()),
        "intensos": int(focos["foco_intenso"].sum()),
    }


def texto_readme(versao_api, resultado, origem) -> str:
    passou = resultado["vetores_iguais"] == resultado["focos"] == resultado["iguais"]
    fora = "; ".join(f"`{nome}`: {', '.join(valores)}" for nome, valores in resultado["fora_do_manifest"].items()
                     if valores) or "nenhum"
    versao_ok = xgb.__version__ == versao_api
    colunas = pacote.nomes_colunas()
    return "\n".join([
        MARCA_INICIO,
        "## C3. Teste do pacote do modelo",
        "",
        f"Gerado por `model/teste_pacote_api.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC, "
        f"com {origem}. É a \"exportação de brinquedo\" do plano, adaptada: o modelo real é um XGBoost "
        "treinado fora do BigQuery ML (ver \"Custos no GCP\"), então a C3 testa o pacote que a Frente C gera "
        f"contra o código da API da Frente D (`{REF_API}`).",
        "",
        "### Resultado",
        "",
        f"- **Versão do XGBoost:** a API fixa `xgboost-cpu=={versao_api}` em `api/requirements.txt`; o "
        f"pacote foi gerado com `xgboost {xgb.__version__}` ({'iguais' if versao_ok else '**diferentes**'}). "
        "O treino da Frente C usa a mesma versão (`model/requirements.txt`).",
        f"- **Carga:** a classe `Modelo` da API carregou o pacote (`{resultado['versao_carregada']}`).",
        f"- **Codificação:** {resultado['vetores_iguais']} de {resultado['focos']} vetores montados pela API "
        f"iguais aos do treino ({resultado['colunas']} colunas).",
        f"- **Paridade:** {resultado['iguais']} de {resultado['focos']} probabilidades iguais; maior "
        f"diferença {resultado['max_diferenca']:.1e}. {'Passou.' if passou and versao_ok else '**Não passou.**'}",
        f"- **Categorias:** valores fora do manifest: {fora}. Focos sem bioma na amostra: "
        f"{resultado['sem_bioma']}; intensos: {resultado['intensos']} de {resultado['focos']}.",
        "",
        "### Passo a passo da preparação das variáveis (para a Frente D)",
        "",
        "É o que a Gold de treino, `model/pacote.py` e `api/app/features.py` + `modelo.py` fazem:",
        "",
        "1. `hora` = `EXTRACT(HOUR FROM data_hora_gmt)` e `mes` = `EXTRACT(MONTH FROM data_hora_gmt)`, em UTC.",
        "2. `tipo_orbita` vem de `focos.satelites` (no pacote, `satelites.json`).",
        "3. Vazio e -999 viram nulo em todas as numéricas; nulo entra no vetor como `NaN` (o XGBoost "
        "trata o ausente).",
        "4. Categóricas em one-hot, uma coluna por categoria na ordem do manifest; nulo ou valor fora da "
        "lista deixa todas as colunas em 0.",
        "5. O vetor segue a ordem de `variaveis` do `manifest.json`, e o Booster lê as colunas pela posição:",
        "",
        *[f"   {i}. `{nome}`" for i, nome in enumerate(colunas)],
        "",
        "### Para a Frente D",
        "",
        "- O pacote real tem o mesmo formato, com `versao_modelo` = `foco_intenso_v1`, em "
        "`gs://<BUCKET>/modelos/foco_intenso/v1/`. Não há export do BigQuery ML: o `api/README.md` "
        "(\"Ainda falta\") e o status (\"D5 depende de C3\") podem ser atualizados.",
        "- `bioma` é obrigatório no `schemas.py` da API, mas há focos sem bioma nos dados (perfil A1). O "
        "modelo aceita bioma nulo (todas as colunas de bioma em 0); se a API aceitar `None`, esses focos "
        "também podem ser pontuados.",
        MARCA_FIM,
    ])


def atualizar_readme(texto) -> None:
    atual = CAMINHO_README.read_text(encoding="utf-8")
    padrao = re.compile(re.escape(MARCA_INICIO) + r".*?" + re.escape(MARCA_FIM), re.DOTALL)
    novo = padrao.sub(lambda _m: texto, atual) if padrao.search(atual) else atual.rstrip("\n") + "\n\n" + texto
    CAMINHO_README.write_text(novo.rstrip("\n") + "\n", encoding="utf-8")
    print(f"\nResultado gravado em {CAMINHO_README}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-readme", action="store_true", help="Só imprime o resultado, sem mexer no README")
    parser.add_argument("--sintetico", action="store_true", help="Usa focos inventados, sem ler o GCP")
    args = parser.parse_args()

    if args.sintetico:
        focos = focos_sinteticos(np.random.default_rng(SEMENTE))
        origem = f"{QTD_FOCOS} focos sintéticos, sem nada no GCP (custo zero)"
    else:
        focos = focos_da_gold()
        origem = f"{QTD_FOCOS} focos reais de treino de `focos.gold_treino`"
    booster = xgb.train(
        {"objective": "binary:logistic", "max_depth": 3, "eta": 0.2, "seed": SEMENTE},
        xgb.DMatrix(pacote.montar_matriz(focos), label=focos["foco_intenso"]),
        num_boost_round=QTD_ARVORES,
    )
    pacote.salvar_pacote(booster, PASTA_PACOTE, VERSAO, pacote.ler_satelites())
    print(f"Pacote gravado em {PASTA_PACOTE}")

    versao_api = copiar_api()
    resultado = validar(focos, booster, carregar_modelo_da_api())

    texto = texto_readme(versao_api, resultado, origem)
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
