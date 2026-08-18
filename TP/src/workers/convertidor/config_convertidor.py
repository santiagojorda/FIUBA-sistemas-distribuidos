import os
from common.constantes_protocolo import (
    ENV_FECHA_INICIO,
    ENV_FECHA_FIN,
)

class ConfigConvertidor:
    def __init__(self):
        self.fecha_inicio = os.environ.get(ENV_FECHA_INICIO, "2022-09-01")
        self.fecha_fin = os.environ.get(ENV_FECHA_FIN, "2022-09-05")
