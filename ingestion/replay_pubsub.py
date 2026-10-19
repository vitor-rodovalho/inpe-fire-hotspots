"""Replay: publica no Pub/Sub os focos dos CSVs diários, na ordem da detecção.

O INPE não oferece um fluxo de eventos, só arquivos. Este script simula o tempo
real em cima dos arquivos diários do bucket: lê os dias pedidos, ordena os focos
pelo horário da detecção e publica cada um como uma mensagem, esperando entre
um horário e o seguinte o intervalo real dividido pelo fator de aceleração.

Mensagem (contrato em docs/contracts.md): JSON com as 16 chaves do CSV e os
valores como vieram, mais publicado_em, atributos id e ts_evento (horário da
detecção, usado pelo Dataflow como tempo do evento).

Com --fracao-invalidas, uma parte sorteada dos focos ganha também uma cópia
estragada, publicada logo depois do original. O foco real segue intacto, então
nenhum dado se perde. A cópia vai para streaming_erros com o id terminado em
"-invalida".

O replay nunca volta no tempo sozinho: ele guarda o último horário publicado e
se recusa a começar antes dele, porque, passados os 10 minutos da deduplicação
do Dataflow, esses focos entrariam de novo na Silver e nos agregados. Para
repetir um período, drene o job (pipeline/drain.sh), recrie as tabelas de
sql/streaming/, suba o job de novo (pipeline/deploy.sh) e use --permitir-voltar.


Com --saida ARQUIVO.jsonl, nada vai para o Pub/Sub: as mensagens são gravadas
num arquivo, que pipeline/run_local.sh --offline lê (teste sem nuvem).

Uso (a partir da raiz do repositório):
    bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fim 2026-10-03
    bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fator 1200 --fracao-invalidas 0.02
    bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --fim 2026-10-07 --somente-contar
    # teste rápido: 200 focos, um a cada 0,1 s, mais 5% de cópias inválidas
    bash ingestion/run.sh replay_pubsub --inicio 2026-10-01 --max-mensagens 200 \\
        --intervalo-fixo 0.1 --fracao-invalidas 0.05
    # teste sem nuvem: CSVs de uma pasta local para um arquivo
    bash ingestion/run.sh replay_pubsub --arquivos dados/raw/diario/*.csv \\
        --fracao-invalidas 0.05 --saida dados/mensagens.jsonl
"""

import argparse
import datetime as dt
import itertools
import json
import os
import random
import sys
import threading
import time
from typing import Any, Literal

from common import PROJECT_ID, TOPICO, ler_csv, uri_diario

# =============================================================================
# Constantes. PROJECT_ID e TOPICO vêm de config.env (via common.py)
# =============================================================================
ATRIBUTO_ID = "id"
ATRIBUTO_TEMPO_EVENTO = "ts_evento"
FORMATO_DATA_INPE = "%Y-%m-%d %H:%M:%S"
FORMATO_TS_EVENTO = "%Y-%m-%dT%H:%M:%SZ"

FATOR_PADRAO = 600  # 1 hora de detecções passa em 6 segundos
ESPERA_MAXIMA_PADRAO_S = 5.0  # Teto de uma espera: madrugadas sem foco não travam a demo
FRACAO_INVALIDAS_PADRAO = 0.0
SUFIXO_ID_INVALIDA = "-invalida"  # Id das cópias estragadas, para reconhecê-las em streaming_erros
SEMENTE_ALEATORIA = 42
PROGRESSO_A_CADA = 1000  # Mensagens entre duas linhas de progresso

LOTE_MAX_MENSAGENS = 500  # O cliente do Pub/Sub agrupa mensagens em lotes
LOTE_MAX_LATENCIA_S = 0.05
LIMITE_PENDENTES = 2000  # Mensagens ainda não confirmadas antes de o envio esperar

ARQUIVO_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".replay_state.json")

CAMPO_ARQUIVO_DADOS = "data"  # Formato de --saida: uma mensagem por linha,
CAMPO_ARQUIVO_ATRIBUTOS = "attributes"  # {"data": corpo, "attributes": {...}}
# =============================================================================


# --- Leitura e ordenação -----------------------------------------------------


def listar_dias(inicio, fim) -> list[str]:
    dia, ultimo = dt.date.fromisoformat(inicio), dt.date.fromisoformat(fim or inicio)
    if ultimo < dia:
        sys.exit("ERRO: --fim é anterior a --inicio.")
    return [(dia + dt.timedelta(days=n)).isoformat() for n in range((ultimo - dia).days + 1)]


def carregar_focos(caminhos) -> tuple[list[Any], int]:
    """
    Lê os CSVs e devolve [(detectado_em, foco)] em ordem de detecção.

    Linhas sem horário legível não podem ganhar o atributo ts_evento e ficam de
    fora (são contadas e informadas).
    """
    focos, sem_horario = [], 0
    for caminho in caminhos:
        try:
            linhas = ler_csv(caminho)
        except Exception as erro:
            print(f"  [ignorado] {caminho}: {type(erro).__name__}: {erro}")
            continue
        for foco in linhas:
            try:
                detectado_em = dt.datetime.strptime((foco.get("data_hora_gmt") or "").strip(), FORMATO_DATA_INPE)
            except ValueError:
                sem_horario += 1
                continue
            focos.append((detectado_em.replace(tzinfo=dt.timezone.utc), foco))
        print(f"  [lido]     {caminho}: {len(linhas)} focos")
    focos.sort(key=lambda par: par[0])
    return focos, sem_horario


def agrupar_por_instante(focos) -> list[tuple[Any, list[Any]]]:
    """[(instante, [focos daquele instante])], na ordem do tempo."""
    return [(instante, [f for _, f in grupo]) for instante, grupo in itertools.groupby(focos, key=lambda p: p[0])]


def calcular_esperas(grupos, fator, espera_maxima):  # -> list[Any]:
    """Espera (s) depois de cada grupo: intervalo real até o próximo / fator, com teto."""
    esperas = []
    for (atual, _), (proximo, _) in zip(grupos, grupos[1:]):
        esperas.append(min((proximo - atual).total_seconds() / fator, espera_maxima))
    return esperas + [0.0]


# --- Mensagens ---------------------------------------------------------------


def estragar(
    foco, sorteio
) -> (
    tuple[Literal['{"id": "quebrado", '], Literal["json_invalido"]]
    | tuple[str, Literal["coordenada_fora_do_brasil"]]
    | tuple[str, Literal["risco_fogo_fora_da_faixa"]]
):
    """Corpo de uma mensagem propositalmente inválida e o motivo que o Dataflow deve registrar."""
    tipo = sorteio.choice(["json", "coordenada", "risco_fogo"])
    if tipo == "json":
        return '{"id": "quebrado", ', "json_invalido"
    foco = dict(foco)
    if tipo == "coordenada":
        foco["lat"], foco["lon"] = "40.7", "-74.0"  # Nova York
        return json.dumps(foco, ensure_ascii=False), "coordenada_fora_do_brasil"
    foco["risco_fogo"] = "7.5"  # a faixa válida é de 0 a 1
    return json.dumps(foco, ensure_ascii=False), "risco_fogo_fora_da_faixa"


def mensagens_do_foco(foco, detectado_em, sorteio, fracao_invalidas):  # -> list[tuple[bytes, dict[str, Any], None]]:
    """O foco real e, numa fração sorteada, também uma cópia estragada dele.

    Devolve [(corpo em bytes, atributos, motivo)]. O motivo é None no foco real
    e, na cópia, o que o Dataflow deve registrar em streaming_erros. A cópia
    ganha um id com sufixo para não se confundir com o foco real.
    """
    foco = dict(foco, publicado_em=dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"))
    atributos = {
        ATRIBUTO_ID: (foco.get("id") or "").strip(),
        ATRIBUTO_TEMPO_EVENTO: detectado_em.strftime(FORMATO_TS_EVENTO),
    }
    mensagens = [(json.dumps(foco, ensure_ascii=False).encode("utf-8"), atributos, None)]
    if fracao_invalidas and sorteio.random() < fracao_invalidas:
        corpo, motivo = estragar(foco, sorteio)
        atributos_copia = dict(atributos, **{ATRIBUTO_ID: atributos[ATRIBUTO_ID] + SUFIXO_ID_INVALIDA})
        mensagens.append((corpo.encode("utf-8"), atributos_copia, motivo))
    return mensagens


# --- Estado entre execuções --------------------------------------------------


def ler_ultimo_instante() -> dt.datetime | None:
    try:
        with open(ARQUIVO_ESTADO, encoding="utf-8") as arquivo:
            return dt.datetime.fromisoformat(json.load(arquivo)["ultimo_instante"])
    except (OSError, KeyError, ValueError):
        return None


def gravar_ultimo_instante(instante) -> None:
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as arquivo:
        json.dump({"ultimo_instante": instante.isoformat(), "gravado_em": dt.datetime.now().isoformat()}, arquivo)


def conferir_volta_no_tempo(primeiro_instante, permitir_voltar) -> None:
    ultimo = ler_ultimo_instante()
    if ultimo is None or primeiro_instante > ultimo or permitir_voltar:
        return
    sys.exit(
        f"ERRO: este período começa em {primeiro_instante:%Y-%m-%d %H:%M}, antes do último foco já publicado "
        f"({ultimo:%Y-%m-%d %H:%M}). Esses focos entrariam de novo na Silver e nos agregados.\n"
        "Escolha um período posterior, ou drene o job, recrie as tabelas de sql/streaming/, "
        "suba o job de novo e rode com --permitir-voltar."
    )


# --- Execução ----------------------------------------------------------------


def formatar_duracao(segundos) -> str:
    minutos, segundos = divmod(int(round(segundos)), 60)
    return f"{minutos} min {segundos:02d} s"


def resumir(focos, grupos, esperas, args) -> None:
    print(f"\n{len(focos)} focos em {len(grupos)} horários distintos")
    if focos:
        print(f"Período simulado: {focos[0][0]:%Y-%m-%d %H:%M} a {focos[-1][0]:%Y-%m-%d %H:%M} (GMT)")
    if args.intervalo_fixo is not None:
        duracao = len(focos) * args.intervalo_fixo
        print(f"Ritmo: 1 mensagem a cada {args.intervalo_fixo} s")
    else:
        duracao = sum(esperas)
        print(
            f"Ritmo: fator {args.fator:g} (1 hora de detecções em {3600 / args.fator:.1f} s), "
            f"espera máxima {args.espera_maxima} s"
        )
    print(f"Duração estimada: {formatar_duracao(duracao)}")


def publicar(grupos, esperas, args) -> dict[str, int]:
    from google.cloud import pubsub_v1  # Importado aqui: o modo --saida não precisa da biblioteca

    publicador = pubsub_v1.PublisherClient(
        batch_settings=pubsub_v1.types.BatchSettings(max_messages=LOTE_MAX_MENSAGENS, max_latency=LOTE_MAX_LATENCIA_S),
        publisher_options=pubsub_v1.types.PublisherOptions(
            flow_control=pubsub_v1.types.PublishFlowControl(
                message_limit=LIMITE_PENDENTES,
                limit_exceeded_behavior=pubsub_v1.types.LimitExceededBehavior.BLOCK,
            )
        ),
    )
    topico = publicador.topic_path(PROJECT_ID, TOPICO)
    sorteio = random.Random(SEMENTE_ALEATORIA)
    contagem = {"focos": 0, "invalidas": 0, "falhas": 0}
    trava = threading.Lock()

    def ao_confirmar(futuro) -> None:
        if futuro.exception() is not None:
            with trava:
                contagem["falhas"] += 1

    print(f"\nPublicando em {topico} (Ctrl+C para parar)")
    inicio, ultimo_publicado = time.monotonic(), None
    try:
        for (instante, focos_do_instante), espera in zip(grupos, esperas):
            for foco in focos_do_instante:
                for corpo, atributos, motivo in mensagens_do_foco(foco, instante, sorteio, args.fracao_invalidas):
                    publicador.publish(topico, corpo, **atributos).add_done_callback(ao_confirmar)
                    contagem["focos" if motivo is None else "invalidas"] += 1
                if contagem["focos"] % PROGRESSO_A_CADA == 0:
                    taxa = contagem["focos"] / max(time.monotonic() - inicio, 1e-9)
                    print(
                        f"  {contagem['focos']:>7} focos publicados | relógio simulado {instante:%Y-%m-%d %H:%M} "
                        f"| {taxa:,.0f} focos/s"
                    )
                if args.intervalo_fixo is not None:
                    time.sleep(args.intervalo_fixo)
            ultimo_publicado = instante
            if args.intervalo_fixo is None:
                time.sleep(espera)
    except KeyboardInterrupt:
        print("\nInterrompido. Enviando o que já estava na fila...")
    finally:
        publicador.stop()  # Envia o que estiver pendente e espera as confirmações
        if ultimo_publicado is not None:
            gravar_ultimo_instante(ultimo_publicado)

    duracao = time.monotonic() - inicio
    print(
        f"\n{contagem['focos']} focos e {contagem['invalidas']} cópias inválidas publicados em "
        f"{formatar_duracao(duracao)} ({contagem['falhas']} falhas de envio)"
    )
    if ultimo_publicado is not None:
        print(f"Último horário publicado: {ultimo_publicado:%Y-%m-%d %H:%M} (gravado em {ARQUIVO_ESTADO})")
    return contagem


def gravar_em_arquivo(grupos, args) -> dict[str, int]:
    """
    Grava as mensagens num arquivo JSON Lines em vez de publicar (teste sem nuvem).

    Cada linha é {"data": corpo, "attributes": atributos}, o que o Pub/Sub
    entregaria ao Dataflow. Sem esperas e sem mexer no estado do replay, porque
    nenhum job está ouvindo.
    """
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    sorteio = random.Random(SEMENTE_ALEATORIA)
    contagem = {"focos": 0, "invalidas": 0}
    with open(args.saida, "w", encoding="utf-8") as saida:
        for instante, focos_do_instante in grupos:
            for foco in focos_do_instante:
                for corpo, atributos, motivo in mensagens_do_foco(foco, instante, sorteio, args.fracao_invalidas):
                    linha = {CAMPO_ARQUIVO_DADOS: corpo.decode("utf-8"), CAMPO_ARQUIVO_ATRIBUTOS: atributos}
                    saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
                    contagem["focos" if motivo is None else "invalidas"] += 1
    print(
        f"\n{contagem['focos']} focos e {contagem['invalidas']} cópias inválidas gravados em {args.saida} "
        "(sem esperas: a duração acima vale só para o Pub/Sub)"
    )
    return contagem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inicio", help="primeiro dia (AAAA-MM-DD), lido de raw/diario/ no bucket")
    parser.add_argument("--fim", help="último dia (AAAA-MM-DD); padrão: o mesmo de --inicio")
    parser.add_argument("--arquivos", nargs="+", help="CSVs (locais ou gs://) no lugar de --inicio/--fim")
    parser.add_argument("--fator", type=float, default=FATOR_PADRAO, help="aceleração do tempo")
    parser.add_argument(
        "--espera-maxima",
        type=float,
        default=ESPERA_MAXIMA_PADRAO_S,
        help="teto, em segundos, de uma espera entre dois horários",
    )
    parser.add_argument(
        "--intervalo-fixo", type=float, help="ignora o tempo real e espera este número de segundos entre mensagens"
    )
    parser.add_argument("--max-mensagens", type=int, help="para depois deste número de focos")
    parser.add_argument(
        "--fracao-invalidas",
        type=float,
        default=FRACAO_INVALIDAS_PADRAO,
        help="fração dos focos que ganha também uma cópia estragada (0 a 1)",
    )
    parser.add_argument("--somente-contar", action="store_true", help="mostra o plano sem publicar nada")
    parser.add_argument("--saida", help="grava as mensagens neste arquivo .jsonl em vez de publicar (teste sem nuvem)")
    parser.add_argument(
        "--permitir-voltar",
        action="store_true",
        help="aceita um período anterior ao último publicado (reinicie o job antes)",
    )
    args = parser.parse_args()

    if not (args.arquivos or args.inicio):
        parser.error("informe --inicio (e opcionalmente --fim) ou --arquivos")
    if args.fator <= 0 or not 0 <= args.fracao_invalidas <= 1:
        parser.error("--fator deve ser positivo e --fracao-invalidas deve estar entre 0 e 1")

    caminhos = args.arquivos or [uri_diario(dia) for dia in listar_dias(args.inicio, args.fim)]
    print(f"Lendo {len(caminhos)} arquivo(s)")
    focos, sem_horario = carregar_focos(caminhos)
    if sem_horario:
        print(f"  {sem_horario} linhas sem horário legível ficaram de fora")
    if args.max_mensagens:
        focos = focos[: args.max_mensagens]
    if not focos:
        sys.exit("ERRO: nenhum foco para publicar.")

    grupos = agrupar_por_instante(focos)
    esperas = calcular_esperas(grupos, args.fator, args.espera_maxima)
    resumir(focos, grupos, esperas, args)
    if args.somente_contar:
        return
    if args.saida:
        gravar_em_arquivo(grupos, args)
        return

    if not PROJECT_ID:
        sys.exit("ERRO: PROJECT_ID não definido. Rode via ingestion/run.sh.")
    conferir_volta_no_tempo(grupos[0][0], args.permitir_voltar)
    publicar(grupos, esperas, args)


if __name__ == "__main__":
    main()
