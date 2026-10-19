"""Baixa os CSVs de focos de calor do INPE e envia para o Cloud Storage.

Arquivos mensais (histórico, batch) vão para gs://BUCKET/raw/mensal/ e
arquivos diários (replay do streaming) vão para gs://BUCKET/raw/diario/.
Com --destino PASTA, tudo vai para uma pasta da máquina, com as mesmas
subpastas, e nada é enviado à nuvem (teste sem GCP).

Rodar duas vezes não duplica nada: um arquivo só é baixado de novo quando o
tamanho no INPE mudou desde o último download. Ao final, o script reescreve o
manifesto (raw/manifesto/arquivos.csv) com o número de linhas de cada
arquivo, que a carga da Bronze usa para conferir a contagem.

Uso (a partir da raiz do repositório):
    bash ingestion/run.sh download_inpe                   # Mensal e diário, para o bucket
    bash ingestion/run.sh download_inpe --tipo mensal
    bash ingestion/run.sh download_inpe --somente-listar
    # teste sem nuvem: um mês e um dia numa pasta local
    bash ingestion/run.sh download_inpe --destino dados --tipo mensal --inicio 2026-08
    bash ingestion/run.sh download_inpe --destino dados --tipo diario --inicio 2026-09-30
"""

import argparse
import csv
import datetime as dt
import http.client
import io
import json
import os
import shutil
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Literal

from common import (
    BUCKET,
    PASTA_MANIFESTO,
    PASTA_RAW_DIARIO,
    PASTA_RAW_MENSAL,
    PROJECT_ID,
    nome_diario,
    nome_mensal,
)

# =============================================================================
# Constantes. Os valores vêm de config.env (carregado por ingestion/run.sh)
# os padrões abaixo são os do contrato do projeto. Nomes do bucket e das pastas
# ficam em common.py, porque o publicador também usa
# =============================================================================
INPE_URL_BASE = os.environ.get("INPE_URL_BASE", "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv")
INPE_PASTA_MENSAL = os.environ.get("INPE_PASTA_MENSAL", "mensal/Brasil")
INPE_PASTA_DIARIO = os.environ.get("INPE_PASTA_DIARIO", "diario/Brasil")

NOME_MANIFESTO = "arquivos.csv"

MES_INICIO = os.environ.get("MES_INICIO", "2025-10")  # AAAA-MM
MES_FIM = os.environ.get("MES_FIM", "2026-09")  # AAAA-MM
DIA_INICIO = os.environ.get("DIA_INICIO", "2026-10-01")  # AAAA-MM-DD
DIA_FIM = os.environ.get("DIA_FIM", "")  # Vazio = ontem

EXTENSOES_TENTADAS = (".csv", ".zip")  # O INPE às vezes publica zipado

TIMEOUT_CONSULTA_S = 30  # Só confere se o arquivo existe e o tamanho dele
TIMEOUT_DOWNLOAD_S = 180
TIMEOUT_ENVIO_S = 120  # Prazo de cada pedaço enviado ao bucket
TAMANHO_PEDACO_ENVIO = 8 * 1024 * 1024  # 8 MB por pedaço enviado ao bucket
TENTATIVAS_REDE = 4  # Tentativas por arquivo quando o INPE não responde (mínimo 1)
ESPERA_INICIAL_S = 5  # Espera antes da 2ª tentativa, então dobra a cada nova tentativa
LIMITE_FALHAS_SEGUIDAS = 3  # Arquivos seguidos que falham antes de concluir que o INPE está fora do ar
TAMANHO_BLOCO = 1024 * 1024
CABECALHO_MANIFESTO = ["uri", "tipo", "linhas", "bytes_csv", "url_origem", "baixado_em"]

SUFIXO_METADADOS_LOCAL = ".meta.json"  # Com --destino, os metadados ficam ao lado de cada CSV
FORMATO_PERIODO = {"mensal": ("%Y-%m", "AAAA-MM"), "diario": ("%Y-%m-%d", "AAAA-MM-DD")}
# =============================================================================


def listar_meses(inicio, fim) -> list[Any]:
    """Lista 'AAAAMM' de inicio até fim (ambos 'AAAA-MM'), inclusive."""
    ano, mes = map(int, inicio.split("-"))
    ano_fim, mes_fim = map(int, fim.split("-"))
    periodos = []
    while (ano, mes) <= (ano_fim, mes_fim):
        periodos.append(f"{ano:04d}{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return periodos


def listar_dias(inicio, fim) -> list[Any]:
    """Lista 'AAAAMMDD' de inicio até fim (ambos 'AAAA-MM-DD'), inclusive."""
    dia = dt.date.fromisoformat(inicio)
    ultimo = dt.date.fromisoformat(fim) if fim else dt.date.today() - dt.timedelta(days=1)
    periodos = []
    while dia <= ultimo:
        periodos.append(dia.strftime("%Y%m%d"))
        dia += dt.timedelta(days=1)
    return periodos


# --- Destinos: bucket ou pasta local -----------------------------------------
# Os dois oferecem as mesmas operações, e o resto do script não sabe qual está
# usando. Os caminhos são relativos à raiz do destino, como "raw/mensal/x.csv"


class DestinoBucket:
    """Arquivos no Cloud Storage; os metadados ficam no próprio objeto."""

    def __init__(self, nome_bucket):
        # Importados aqui pois o destino local não precisa da nuvem
        import requests
        from google.cloud import storage
        from google.cloud.storage.retry import DEFAULT_RETRY

        self._cliente = storage.Client(project=PROJECT_ID or None)
        # Sem isso, a biblioteca não repete um envio que falha no meio
        self._repeticao_envio = DEFAULT_RETRY
        self._erros_envio = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        self._bucket = self._cliente.bucket(nome_bucket)
        self.descricao = f"gs://{nome_bucket}"

    def uri(self, caminho) -> str:
        return f"gs://{self._bucket.name}/{caminho}"

    def metadados(self, caminho) -> Any | dict[Any, Any] | None:
        """Metadados de um arquivo já enviado, ou None se ele não existir."""
        blob = self._bucket.blob(caminho)
        if not blob.exists():
            return None
        blob.reload()
        return blob.metadata or {}

    def enviar(self, arquivo_local, caminho, metadados) -> None:
        """
        Envia o arquivo em pedaços de TAMANHO_PEDACO_ENVIO.

        Um pedaço que falha é reenviado sozinho, com espera crescente. Se a conexão
        continuar falhando, o erro vira ConnectionError, e o arquivo aparece como [falhou].
        """
        blob = self._bucket.blob(caminho, chunk_size=TAMANHO_PEDACO_ENVIO)
        blob.metadata = metadados
        try:
            blob.upload_from_filename(
                arquivo_local, content_type="text/csv", timeout=TIMEOUT_ENVIO_S, retry=self._repeticao_envio
            )
        except self._erros_envio as erro:
            raise ConnectionError(f"envio ao bucket falhou: {erro}") from erro

    def listar_csvs(self, pasta) -> list[tuple[str, Any, Any | dict[Any, Any]]]:
        """[(uri, bytes, metadados)] dos CSVs de uma pasta."""
        return [
            (self.uri(blob.name), blob.size, blob.metadata or {})
            for blob in self._cliente.list_blobs(self._bucket, prefix=pasta + "/")
            if blob.name.endswith(".csv")
        ]

    def gravar_texto(self, caminho, texto) -> None:
        self._bucket.blob(caminho).upload_from_string(texto, content_type="text/csv")


class DestinoLocal:
    """Arquivos numa pasta da máquina; os metadados ficam num .meta.json ao lado de cada CSV."""

    def __init__(self, raiz) -> None:
        self._raiz = raiz
        self.descricao = os.path.abspath(raiz)

    def uri(self, caminho) -> Any:
        return os.path.join(self._raiz, caminho)

    def metadados(self, caminho) -> Any | dict[Any, Any] | None:
        if not os.path.exists(self.uri(caminho)):
            return None
        try:
            with open(self.uri(caminho) + SUFIXO_METADADOS_LOCAL, encoding="utf-8") as arquivo:
                return json.load(arquivo)
        except (OSError, ValueError):
            return {}

    def enviar(self, arquivo_local, caminho, metadados) -> None:
        os.makedirs(os.path.dirname(self.uri(caminho)), exist_ok=True)
        shutil.copyfile(arquivo_local, self.uri(caminho))
        with open(self.uri(caminho) + SUFIXO_METADADOS_LOCAL, "w", encoding="utf-8") as arquivo:
            json.dump(metadados, arquivo, ensure_ascii=False, indent=2)

    def listar_csvs(self, pasta) -> list[tuple[str, Any, Any | dict[Any, Any]]]:
        if not os.path.isdir(self.uri(pasta)):
            return []
        return [
            (
                self.uri(f"{pasta}/{nome}"),
                os.path.getsize(self.uri(f"{pasta}/{nome}")),
                self.metadados(f"{pasta}/{nome}") or {},
            )
            for nome in sorted(os.listdir(self.uri(pasta)))
            if nome.endswith(".csv")
        ]

    def gravar_texto(self, caminho, texto) -> None:
        os.makedirs(os.path.dirname(self.uri(caminho)), exist_ok=True)
        with open(self.uri(caminho), "w", encoding="utf-8", newline="") as arquivo:
            arquivo.write(texto)


# --- INPE --------------------------------------------------------------------


# Falhas passageiras de conexão (sem resposta, conexão caída, download cortado)
ERROS_DE_REDE = (urllib.error.URLError, http.client.HTTPException, ssl.SSLError, TimeoutError, ConnectionError)


def com_novas_tentativas(funcao, *args) -> Any:
    """
    Chama funcao(*args) e, numa falha de rede, espera e tenta de novo.

    Um erro HTTP de verdade (por exemplo 403) não é repetido; um erro 5xx, sim.
    A última tentativa fica fora do laço: se ela também falhar, o erro sobe para
    quem chamou. TENTATIVAS_REDE menor que 1 vale como 1.
    """
    tentativas = max(1, TENTATIVAS_REDE)
    espera = ESPERA_INICIAL_S
    for tentativa in range(1, tentativas):
        try:
            return funcao(*args)
        except urllib.error.HTTPError as erro:
            if erro.code < 500:
                raise
            motivo = f"HTTP {erro.code}"
        except ERROS_DE_REDE as erro:
            motivo = getattr(erro, "reason", None) or type(erro).__name__
        print(f"    [rede] tentativa {tentativa} de {tentativas} falhou ({motivo}); nova tentativa em {espera} s")
        time.sleep(espera)
        espera *= 2
    return funcao(*args)


def tamanho_remoto(url) -> int | None:
    """Tamanho do arquivo no INPE em bytes, ou None se ele não existir."""
    requisicao = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_CONSULTA_S) as resposta:
            return int(resposta.headers.get("Content-Length", -1))
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return None
        raise


def localizar_no_inpe(url_sem_extensao) -> tuple[str | None, str | None, int | None]:
    """Tenta cada extensão e devolve (url, extensao, tamanho) da primeira que existir."""
    for extensao in EXTENSOES_TENTADAS:
        url = url_sem_extensao + extensao
        tamanho = com_novas_tentativas(tamanho_remoto, url)
        if tamanho is not None:
            return url, extensao, tamanho
    return None, None, None


def baixar(url, destino) -> None:
    with urllib.request.urlopen(url, timeout=TIMEOUT_DOWNLOAD_S) as resposta, open(destino, "wb") as saida:
        shutil.copyfileobj(resposta, saida, TAMANHO_BLOCO)


def extrair_csv_do_zip(caminho_zip, destino_csv) -> None:
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        nomes_csv = [n for n in arquivo_zip.namelist() if n.lower().endswith(".csv")]
        if len(nomes_csv) != 1:
            raise ValueError(f"{caminho_zip}: esperado 1 CSV dentro do zip, achei {nomes_csv}")
        with arquivo_zip.open(nomes_csv[0]) as origem, open(destino_csv, "wb") as saida:
            shutil.copyfileobj(origem, saida, TAMANHO_BLOCO)


def contar_linhas_de_dados(caminho_csv) -> int:
    """Número de registros do CSV, sem contar o cabeçalho."""
    with open(caminho_csv, newline="", encoding="utf-8", errors="replace") as arquivo:
        return max(sum(1 for _ in csv.reader(arquivo)) - 1, 0)


def processar(
    destino, tipo, periodo, forcar, somente_listar
) -> Literal["ausente"] | Literal["existente"] | Literal["a_baixar"] | Literal["enviado"]:
    """Baixa um arquivo do INPE e envia ao destino se for novo ou tiver mudado."""
    if tipo == "mensal":
        nome = nome_mensal(periodo)
        url_base, pasta_destino = f"{INPE_URL_BASE}/{INPE_PASTA_MENSAL}/{nome}", PASTA_RAW_MENSAL
    else:
        nome = nome_diario(periodo)
        url_base, pasta_destino = f"{INPE_URL_BASE}/{INPE_PASTA_DIARIO}/{nome}", PASTA_RAW_DIARIO

    url, extensao, tamanho = localizar_no_inpe(url_base)
    if url is None:
        print(f"  [ausente no INPE] {nome}")
        return "ausente"

    caminho = f"{pasta_destino}/{nome}.csv"
    metadados = destino.metadados(caminho)
    if metadados is not None and not forcar and metadados.get("tamanho_remoto") == str(tamanho):
        print(f"  [já no destino]   {nome}")
        return "existente"

    if somente_listar:
        print(f"  [a baixar]        {nome}{extensao} ({tamanho / 1e6:.1f} MB)")
        return "a_baixar"

    with tempfile.TemporaryDirectory() as pasta_tmp:
        baixado = os.path.join(pasta_tmp, nome + extensao)
        com_novas_tentativas(baixar, url, baixado)
        caminho_csv = os.path.join(pasta_tmp, nome + ".csv")
        if extensao == ".zip":
            extrair_csv_do_zip(baixado, caminho_csv)
        linhas = contar_linhas_de_dados(caminho_csv)
        destino.enviar(
            caminho_csv,
            caminho,
            {
                "url_origem": url,
                "tamanho_remoto": str(tamanho),
                "linhas": str(linhas),
                "tipo": tipo,
                "baixado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            },
        )
    print(f"  [enviado]         {nome}.csv ({linhas} linhas)")
    return "enviado"


def reescrever_manifesto(destino) -> None:
    """Reconstrói o manifesto a partir dos metadados dos arquivos no destino."""
    linhas = []
    for pasta in (PASTA_RAW_MENSAL, PASTA_RAW_DIARIO):
        for uri, tamanho, meta in destino.listar_csvs(pasta):
            linhas.append(
                [
                    uri,
                    meta.get("tipo", ""),
                    meta.get("linhas", ""),
                    tamanho,
                    meta.get("url_origem", ""),
                    meta.get("baixado_em", ""),
                ]
            )
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(CABECALHO_MANIFESTO)
    escritor.writerows(sorted(linhas))
    destino.gravar_texto(f"{PASTA_MANIFESTO}/{NOME_MANIFESTO}", saida.getvalue())
    total_mensal = sum(int(l[2] or 0) for l in linhas if l[1] == "mensal")
    total_diario = sum(int(l[2] or 0) for l in linhas if l[1] == "diario")
    total_bytes = sum(l[3] for l in linhas)
    print(f"\nManifesto: {len(linhas)} arquivos, {total_bytes / 1e6:.1f} MB em {destino.descricao}")
    print(f"  linhas mensais: {total_mensal}   linhas diárias: {total_diario}")


def listar_tarefas(args) -> list[tuple[str, Any]] | list[Any]:
    """[(tipo, periodo)] a conferir: o período de --inicio/--fim ou, sem eles, o do config.env."""
    if args.inicio:
        fim = args.fim or args.inicio
        if args.tipo == "mensal":
            return [("mensal", p) for p in listar_meses(args.inicio, fim)]
        return [("diario", p) for p in listar_dias(args.inicio, fim)]
    tarefas = []
    if args.tipo in ("mensal", "todos"):
        tarefas += [("mensal", p) for p in listar_meses(MES_INICIO, MES_FIM)]
    if args.tipo in ("diario", "todos"):
        tarefas += [("diario", p) for p in listar_dias(DIA_INICIO, DIA_FIM)]
    return tarefas


def conferir_periodo(parser, args) -> None:
    if args.fim and not args.inicio:
        parser.error("--fim exige --inicio")
    if not args.inicio:
        return
    if args.tipo == "todos":
        parser.error("--inicio e --fim exigem --tipo mensal ou --tipo diario")
    formato, exemplo = FORMATO_PERIODO[args.tipo]
    for valor in filter(None, (args.inicio, args.fim)):
        try:
            dt.datetime.strptime(valor, formato)
        except ValueError:
            parser.error(f"com --tipo {args.tipo}, use datas no formato {exemplo} (recebi {valor!r})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tipo", choices=["mensal", "diario", "todos"], default="todos")
    parser.add_argument("--forcar", action="store_true", help="baixa de novo mesmo se já estiver no destino")
    parser.add_argument("--somente-listar", action="store_true", help="mostra o que seria baixado, sem baixar")
    parser.add_argument("--destino", help="pasta local no lugar do bucket (teste sem nuvem), por exemplo: dados")
    parser.add_argument(
        "--inicio", help="primeiro período, no lugar do config.env: AAAA-MM (mensal) ou AAAA-MM-DD (diario)"
    )
    parser.add_argument("--fim", help="último período; padrão: o mesmo de --inicio")
    args = parser.parse_args()
    conferir_periodo(parser, args)

    if args.destino:
        destino = DestinoLocal(args.destino)
    elif BUCKET:
        destino = DestinoBucket(BUCKET)
    else:
        sys.exit("ERRO: BUCKET não definido. Rode via ingestion/run.sh ou use --destino PASTA.")

    tarefas = listar_tarefas(args)
    print(f"{len(tarefas)} arquivos para conferir em {INPE_URL_BASE}")
    print(f"Destino: {destino.descricao}")
    resultado, falhas_seguidas = {}, 0
    for indice, (tipo, periodo) in enumerate(tarefas):
        try:
            situacao = processar(destino, tipo, periodo, args.forcar, args.somente_listar)
        except ERROS_DE_REDE as erro:
            print(f"  [falhou]          {tipo} {periodo}: {getattr(erro, 'reason', None) or erro}")
            situacao = "falhou"
        resultado[situacao] = resultado.get(situacao, 0) + 1
        falhas_seguidas = falhas_seguidas + 1 if situacao == "falhou" else 0
        restantes = len(tarefas) - indice - 1
        if falhas_seguidas == LIMITE_FALHAS_SEGUIDAS and restantes:
            print(
                f"\n  {falhas_seguidas} arquivos seguidos falharam: o INPE parece fora do ar. "
                f"Os outros {restantes} ficaram sem conferir."
            )
            resultado["nao_conferido"] = restantes
            break
    print("\nResumo:", ", ".join(f"{k}={v}" for k, v in sorted(resultado.items())))

    if not args.somente_listar:
        reescrever_manifesto(destino)
    if resultado.get("falhou"):
        sys.exit(
            "\nAlguns arquivos falharam (veja [falhou] acima). Se foi a rede, rode o mesmo "
            "comando de novo: o que já está no destino não é baixado outra vez."
        )


if __name__ == "__main__":
    main()
