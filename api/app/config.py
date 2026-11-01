"""Configuração da API, lida de variáveis de ambiente.

No Cloud Run, as variáveis são definidas pelo api/deploy.sh. Na máquina local,
os valores padrão apontam para o pacote gerado por modelo_provisorio/treinar.py.
"""

import os

# =============================================================================
# Constantes
# =============================================================================
# Onde está o pacote do modelo: pasta local ou prefixo no Cloud Storage
# (por exemplo gs://inpe-fire-hotspots-data/modelos/foco_intenso/v1)
MODELO_URI = os.environ.get("MODELO_URI", "modelo_local")

# Token fixo exigido em POST /predict (cabeçalho "Authorization: Bearer <token>").
# Vazio desliga a checagem: só para rodar na máquina. O deploy recusa subir sem ele.
API_TOKEN = os.environ.get("API_TOKEN", "")
# =============================================================================
