import hashlib
from common.logger import obtener_logger

logger = obtener_logger(__name__)


def normalizar_valor_hash(valor):
    if valor is None:
        return "N/A"

    valor_normalizado = str(valor).strip()
    return valor_normalizado if valor_normalizado else "N/A"

def obtener_id_shard(valor_hash: str, total_shards: int) -> int:
    hash_hex = hashlib.md5(normalizar_valor_hash(valor_hash).encode('utf-8')).hexdigest()
    return (int(hash_hex, 16) % total_shards) + 1

class ShardHasher:
    HEX_BASE = 16
    SHARD_OFFSET = 1

    @classmethod
    def obtener_id_shard(cls, valor_hash: str, total_shards: int) -> int:
        hash_hex = hashlib.md5(str(valor_hash).encode('utf-8')).hexdigest()
        return (int(hash_hex, cls.HEX_BASE) % total_shards) + cls.SHARD_OFFSET