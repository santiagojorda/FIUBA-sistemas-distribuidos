import os
from common.constantes_protocolo import (
    ENV_CAMPO_FILTRO,
    ENV_OPERADOR_FILTRO,
    ENV_VALOR_FILTRO,
)
from operadores import OP_IGUAL

class ConfigFiltro:
    def __init__(self):
        self.campo_objetivo = os.environ[ENV_CAMPO_FILTRO]
        self.operador_str = os.environ.get(ENV_OPERADOR_FILTRO, OP_IGUAL).lower()
        self.valor_objetivo_crudo = os.environ[ENV_VALOR_FILTRO]
