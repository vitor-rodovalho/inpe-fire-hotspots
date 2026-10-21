"""C3. Teste do pacote do modelo contra a API (a "exportação de brinquedo" do plano).

O modelo real vai ser um XGBoost treinado aqui, fora do BigQuery ML (a reserva
do plano; ver "Custos no GCP" no README). Esta etapa prova, antes do modelo
real, que o pacote que a Frente C gera é lido pela API da Frente D e dá a mesma
resposta:

  1. treina um XGBoost pequeno com 500 focos sintéticos, com as variáveis e as
     categorias reais (nada roda no GCP, custo zero);
  2. grava o pacote (model/pacote.py) em dados/pacote_teste/;
  3. copia o código da API da branch da Frente D (git show, só leitura) para
     dados/api_frente_d/ e carrega o pacote com a classe Modelo de lá;
  4. compara, foco a foco, o vetor montado pela API com o do treino e a
     probabilidade da API com a do Booster;
  5. grava a versão do XGBoost e o passo a passo da preparação das variáveis em
     model/README.md, na seção da C3.

Uso (a partir da raiz do repositório, com o xgboost da API instalado):
    pip install -r model/requirements.txt
    git fetch origin frente-d/api
    python3 model/teste_pacote_api.py
"""

import argparse
import datetime as dt
import importlib
import math
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
    return {chave: (None if isinstance(valor, float) and math.isnan(valor) else valor)
            for chave, valor in foco.items() if chave != "foco_intenso"}


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
    }


def texto_readme(versao_api, resultado) -> str:
    passou = resultado["vetores_iguais"] == resultado["focos"] == resultado["iguais"]
    versao_ok = xgb.__version__ == versao_api
    colunas = pacote.nomes_colunas()
    return "\n".join([
        MARCA_INICIO,
        "## C3. Teste do pacote do modelo",
        "",
        f"Gerado por `model/teste_pacote_api.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC, "
        "sem nada no GCP (custo zero). É a \"exportação de brinquedo\" do plano, adaptada: o modelo real é um XGBoost treinado fora do BigQuery ML (ver "
        "\"Custos no GCP\"), então a C3 testa o pacote que a Frente C gera contra o código da API da "
        f"Frente D (`{REF_API}`).",
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
    args = parser.parse_args()

    focos = focos_sinteticos(np.random.default_rng(SEMENTE))
    booster = xgb.train(
        {"objective": "binary:logistic", "max_depth": 3, "eta": 0.2, "seed": SEMENTE},
        xgb.DMatrix(pacote.montar_matriz(focos), label=focos["foco_intenso"]),
        num_boost_round=QTD_ARVORES,
    )
    pacote.salvar_pacote(booster, PASTA_PACOTE, VERSAO, pacote.ler_satelites())
    print(f"Pacote gravado em {PASTA_PACOTE}")

    versao_api = copiar_api()
    resultado = validar(focos, booster, carregar_modelo_da_api())

    texto = texto_readme(versao_api, resultado)
    print("\n" + texto)
    if not args.sem_readme:
        atualizar_readme(texto)


if __name__ == "__main__":
    main()
