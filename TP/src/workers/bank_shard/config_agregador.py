import os
from common.persistencia import VOLUMEN_DIR
from constantes import PREFIJO_BANK_SHARD, ENV_TOTAL_TX_UPSTREAM, ENV_TOTAL_BANK_UPSTREAM


class ConfigAgregador:
    def __init__(self, id_nodo: int):
        self.base_dir = VOLUMEN_DIR
        self.prefijo_nodo = f"{PREFIJO_BANK_SHARD}_{id_nodo}"
        self.total_tx_upstream = int(os.getenv(ENV_TOTAL_TX_UPSTREAM, "1"))
        self.total_bank_upstream = int(os.getenv(ENV_TOTAL_BANK_UPSTREAM, "1"))
