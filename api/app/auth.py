"""Autenticação por token fixo: "Authorization: Bearer <token>" em POST /predict.

A API é pública no Cloud Run (a URL vai para o professor), então o token evita
que qualquer pessoa com a URL use o modelo. /health e /docs continuam abertos:
um aquece o serviço, o outro mostra o contrato (e tem o botão "Authorize").

O token vem da variável API_TOKEN. Vazia, a checagem fica desligada, para rodar
na máquina; o api/deploy.sh recusa publicar sem ela.
"""

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

# auto_error=False: a resposta de erro é a nossa (401), e não o 403 padrão do FastAPI
esquema = HTTPBearer(auto_error=False, description="Token fixo da API (variável API_TOKEN)")


def exigir_token(credenciais: HTTPAuthorizationCredentials | None = Depends(esquema)) -> None:
    if not config.API_TOKEN:
        return
    # compare_digest: o tempo da comparação não revela quantos caracteres acertaram
    if credenciais is None or not secrets.compare_digest(credenciais.credentials.encode(), config.API_TOKEN.encode()):
        raise HTTPException(
            status_code=401,
            detail="Token ausente ou inválido. Envie o cabeçalho Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
