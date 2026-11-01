# Imagem da API foco intenso para o Cloud Run.
#
# O modelo não fica na imagem: a API baixa o pacote de MODELO_URI (gs://...)
# quando sobe. Assim, trocar o modelo não exige reconstruir a imagem.
#
# Teste local, com o pacote de modelo_local/ montado no contêiner:
#   docker build -t api-foco-intenso api/
#   docker run --rm -p 8080:8080 -e MODELO_URI=/modelo -v "$PWD/api/modelo_local:/modelo:ro" api-foco-intenso

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

# O XGBoost usa OpenMP (libgomp), que a imagem slim não traz
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependências antes do código: mudar o código não refaz esta camada
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Roda sem privilégios de root
RUN useradd --uid 10001 --no-create-home api
USER api

EXPOSE 8080

# O Cloud Run define PORT; "exec" faz o uvicorn receber o sinal de parada
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
