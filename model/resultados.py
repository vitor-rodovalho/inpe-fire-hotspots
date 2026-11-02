"""C7. Resultados: o material do slide de resultados, medido e escrito em docs/model_results.md.

Junta, num documento só, o que o plano pede para os resultados:

  1. o modelo contra os dois baselines no mês de teste (sql/modelo/03_avaliacao.sql);
  2. a importância das variáveis (sql/modelo/05_importancia_variaveis.sql,
     ML.FEATURE_IMPORTANCE);
  3. o monitoramento em produção: os focos de streaming de outubro contra o mês
     de teste (sql/demo/08_model_monitoring.sql, sobre a vw_previsoes);
  4. as estimativas dos focos sem FRP, por satélite (vw_previsoes, uso = 'estimativa');
  5. as limitações que o slide precisa dizer.

Todas as consultas têm dry run antes e teto de bytes; somam algumas centenas de
MB (menos de US$ 0,01). A importância das variáveis só lê os metadados do modelo.

Uso (a partir da raiz do repositório):
    set -a; source config.env; set +a
    python3 model/resultados.py
"""

import datetime as dt

import pandas as pd

import previsoes_monitoramento as c6
import sinal_modelo

# =============================================================================
# Constantes
# =============================================================================
CAMINHO_DOCS = c6.RAIZ_REPO / "docs" / "model_results.md"
NOMES_MODELOS = {
    "modelo_foco_intenso": "**Modelo (boosted tree do BigQuery ML)**",
    "baseline_logistica": "Baseline B: regressão logística só com órbita e hora",
    "baseline_majoritaria": "Baseline A: sempre \"não intenso\"",
}
# =============================================================================


def medir() -> dict:
    tabela = f"`{c6.PROJECT_ID}.{c6.DATASET}"
    conjuntos, _ = c6.consultar(
        f"SELECT conjunto, COUNT(*) AS focos, AVG(IF(foco_intenso, 1, 0)) AS pct_intensos "
        f"FROM {tabela}.gold_treino` GROUP BY conjunto", "conjuntos da Gold")
    avaliacao, _ = c6.consultar(c6.renderizar("sql/modelo/03_avaliacao.sql"), "modelo contra baselines")
    importancia, _ = c6.consultar(c6.renderizar("sql/modelo/05_importancia_variaveis.sql"), "importância")
    monitoramento, _ = c6.consultar(c6.renderizar(c6.CONSULTA_DEMO), "monitoramento")
    estimativas, _ = c6.consultar(
        f"""SELECT satelite, tipo_orbita, COUNT(*) AS focos, AVG(probabilidade_intenso) AS prob_media,
              AVG(IF(previsto_intenso, 1, 0)) AS pct_previstos
            FROM {tabela}.vw_previsoes` WHERE uso = 'estimativa'
            GROUP BY satelite, tipo_orbita ORDER BY focos DESC""", "estimativas por satélite")
    return {"conjuntos": conjuntos.set_index("conjunto"), "avaliacao": avaliacao.set_index("modelo"),
            "importancia": importancia, "monitoramento": monitoramento, "estimativas": estimativas}


def pct(valor, casas=1) -> str:
    return c6.numero(100 * valor, casas) + "%"


def texto_docs(r) -> str:
    n = c6.numero
    conjuntos, avaliacao, importancia = r["conjuntos"], r["avaliacao"], r["importancia"]
    monitoramento, estimativas = r["monitoramento"].set_index("periodo"), r["estimativas"]
    auc = avaliacao.loc["modelo_foco_intenso", "roc_auc_exato"]
    auc_b = avaliacao.loc["baseline_logistica", "roc_auc_exato"]
    acuracia_a = avaliacao.loc["baseline_majoritaria", "accuracy"]
    teste = monitoramento.iloc[0]
    outubro = monitoramento.loc["streaming, todas as horas"]
    sem_frp = monitoramento.loc["streaming sem FRP (só estimativa)", "focos"]
    clima = importancia[importancia["variavel"].isin(["risco_fogo", "numero_dias_sem_chuva", "precipitacao"])]
    geografia = importancia[importancia["variavel"].isin(["lat", "lon", "bioma"])]
    polar = estimativas[estimativas["tipo_orbita"] == "polar"]

    return "\n".join([
        "# Resultados do modelo",
        "",
        f"Gerado por `model/resultados.py` em {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC. É o material "
        "do slide de resultados: o modelo contra os baselines, o que ele usa para decidir, como se comporta nos "
        "focos que chegam pelo streaming e o que precisa ser dito como limitação. As métricas da avaliação estão "
        "em detalhe em [model_metrics.md](model_metrics.md).",
        "",
        "## O modelo",
        "",
        "Um classificador *boosted tree* do BigQuery ML (`focos.modelo_foco_intenso`, registrado no Vertex AI "
        "como `v1`) que estima a probabilidade de um foco de calor ser **intenso**, isto é, de ter FRP acima do "
        "percentil 90 da sua órbita (202,1 MW nos geoestacionários e 28,4 MW nos polares). Usa só o que se sabe "
        "no momento da detecção: posição, hora, mês, tipo de órbita, bioma e clima.",
        "",
        f"- **Treino:** {sinal_modelo.milhar(conjuntos.loc['treino', 'focos'])} focos de out/2025 a ago/2026 "
        f"({pct(conjuntos.loc['treino', 'pct_intensos'])} intensos).",
        f"- **Teste:** {sinal_modelo.milhar(conjuntos.loc['teste', 'focos'])} focos de set/2026 "
        f"({pct(conjuntos.loc['teste', 'pct_intensos'])} intensos). A divisão é por tempo, e não por sorteio, "
        "porque focos vizinhos são quase cópias.",
        "",
        "## 1. Modelo contra os baselines (mês de teste)",
        "",
        "| Modelo | ROC AUC | Precisão | Recall | Acurácia |",
        "|---|---|---|---|---|",
        *[f"| {NOMES_MODELOS[m]} | {n(linha.roc_auc_exato)} | {n(linha.precision)} | {n(linha.recall)} | "
          f"{n(linha.accuracy)} |" for m, linha in avaliacao.iterrows()],
        "",
        f"O critério do plano é ROC AUC de pelo menos 0,70 e ganhar claramente da regressão logística: o modelo "
        f"tem {n(auc)}, {n(auc - auc_b)} acima dela. O ROC AUC é a chance de o modelo dar nota maior a um foco "
        "intenso do que a um não intenso (0,5 é o acaso). A acurácia não serve de critério: responder sempre "
        f"\"não intenso\" acerta {pct(acuracia_a)}.",
        "",
        "## 2. O que o modelo usa para decidir",
        "",
        "Participação de cada variável no ganho do modelo (`ML.FEATURE_IMPORTANCE`):",
        "",
        "| Variável | Participação no ganho | Vezes usada nas árvores |",
        "|---|---|---|",
        *[f"| `{linha.variavel}` | {n(linha.pct_ganho, 1)}% | {sinal_modelo.milhar(linha.vezes_usada)} |"
          for linha in importancia.itertuples()],
        "",
        f"- **`hora` e `tipo_orbita` somam {n(importancia.pct_ganho.iloc[:2].sum(), 0)}% do ganho.** O fogo é "
        "mais forte à tarde, mas a hora também indica qual satélite passou (os polares cruzam em horários fixos), "
        "e sensores diferentes medem energias diferentes. Parte do que o modelo aprende é \"qual instrumento "
        "mediu\".",
        f"- **Onde o foco está** (`lat`, `lon` e `bioma`) soma {n(geografia.pct_ganho.sum(), 0)}%.",
        f"- **O clima no ponto** (risco de fogo, dias sem chuva e precipitação) soma "
        f"{n(clima.pct_ganho.sum(), 0)}%: ajuda, mas pesa menos do que se esperaria.",
        "",
        "## 3. O modelo em produção (streaming)",
        "",
        "Os focos que chegam pelo streaming (outubro de 2026) são pontuados pela `vw_previsoes`. Nos que têm FRP, "
        "a previsão é comparada com o real, com o mesmo limiar de decisão de 0,5 do teste:",
        "",
        "| Período | Focos | Acurácia | Precisão | Recall |",
        "|---|---|---|---|---|",
        *[f"| {periodo} | {sinal_modelo.milhar(linha.focos)} | {n(linha.acuracia)} | {n(linha.precisao)} | "
          f"{n(linha.recall)} |" for periodo, linha in monitoramento.iterrows() if not pd.isna(linha.acuracia)],
        "",
        f"**O modelo se mantém fora do período de treino:** em outubro, a precisão foi de {n(outubro.precisao)} "
        f"e o recall de {n(outubro.recall)}, contra {n(teste.precisao)} e {n(teste.recall)} em setembro. Com a "
        "demo ao vivo, a linha da última hora muda à medida que os focos chegam.",
        "",
        "## 4. Estimativas para os focos sem FRP",
        "",
        f"Em outubro, {sinal_modelo.milhar(sem_frp)} focos chegaram sem FRP. Para eles, a previsão é a única "
        "informação de intensidade, e fica separada do que foi medido (`uso = 'estimativa'`):",
        "",
        "| Satélite | Órbita | Focos | Probabilidade média | Marcados como intensos |",
        "|---|---|---|---|---|",
        *[f"| {linha.satelite} | {linha.tipo_orbita} | {sinal_modelo.milhar(linha.focos)} | {n(linha.prob_media)} | "
          f"{pct(linha.pct_previstos, 0)} |" for linha in estimativas.itertuples()],
        "",
        f"Na órbita polar, os satélites sem FRP recebem probabilidade média de {n(polar.prob_media.mean(), 2)}: "
        "eles nunca aparecem no treino, porque sem FRP não há rótulo, e o modelo os trata como qualquer foco da "
        "órbita polar, com as mesmas variáveis. É uma extrapolação, e deve ser apresentada assim.",
        "",
        "## 5. Limitações (para dizer no slide)",
        "",
        "- **O limiar de \"intenso\" é nosso.** O INPE não tem escala oficial, e o FRP de um foco isolado é "
        "impreciso: o resultado é uma triagem, não uma medida.",
        "- **Na órbita polar, \"intenso\" depende em parte do sensor.** Com um limiar único por órbita, a parcela "
        "de intensos vai de 38% (AQUA) a 0,8% (NPP-375D).",
        "- **A probabilidade não é calibrada.** O treino dá mais peso à classe rara, e com o limiar de 0,5 o "
        f"modelo marca intensos demais: a acurácia ({n(avaliacao.loc['modelo_foco_intenso', 'accuracy'])}) fica "
        f"abaixo da de quem sempre diz \"não\" ({n(acuracia_a)}). Para ordenar os focos (triagem), o que vale é o "
        "ROC AUC.",
        "- **As estimativas dos satélites sem FRP são extrapolação** (seção 4).",
        "",
        "## Como reproduzir",
        "",
        "```bash",
        "set -a; source config.env; set +a",
        "python3 model/treino_avaliacao.py         # treino e avaliação (docs/model_metrics.md)",
        "python3 model/previsoes_monitoramento.py  # views de previsões e monitoramento",
        "python3 model/resultados.py               # este documento",
        "```",
        "",
    ])


def main() -> None:
    print("Medindo:")
    texto = texto_docs(medir())
    CAMINHO_DOCS.write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"Gravado em {CAMINHO_DOCS}")


if __name__ == "__main__":
    main()
