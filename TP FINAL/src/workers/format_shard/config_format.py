from common.persistencia import VOLUMEN_DIR
from constantes import PREFIJO_FORMATEADOR_SHARD


class ConfigFormateador:

    def __init__(self, id_nodo: int):
        self.base_dir = VOLUMEN_DIR
        self.prefijo_nodo = f"{PREFIJO_FORMATEADOR_SHARD}_{id_nodo}"
