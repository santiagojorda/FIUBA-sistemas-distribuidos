import threading
from common.logger import obtener_logger
from common.persistencia import PersistidorEstado, TAMANIO_BATCH_PERSISTENCIA, VOLUMEN_DIR

logger = obtener_logger(__name__)


class DedupFilter:
    """
    Tracks processed request_ids per client to discard duplicate batch deliveries.

    A message without request_id is always considered new (backwards compatible).
    State is persisted atomically to disk so it survives worker restarts.
    """

    def __init__(self, node_name: str, base_dir: str = VOLUMEN_DIR):
        self._persistidor = PersistidorEstado(f"dedup_{node_name}", base_dir=base_dir)
        self._seen: dict[str, set[str]] = {}
        self._lock = threading.Lock()
        self._dirty_count = 0
        self._cargar()

    def _cargar(self):
        estado = self._persistidor.cargar()
        for client_id, ids in estado.items():
            self._seen[client_id] = set(ids)
        if self._seen:
            logger.info(f"Recuperados IDs procesados de {len(self._seen)} clientes.")

    def _persistir(self):
        self._persistidor.guardar({
            cid: list(ids) for cid, ids in self._seen.items()
        })

    def es_duplicado(self, client_id: str, request_id: str | None) -> bool:
        if not request_id:
            return False
        with self._lock:
            return request_id in self._seen.get(client_id, set())

    def marcar_procesado(self, client_id: str, request_id: str | None):
        if not request_id:
            return
        with self._lock:
            if client_id not in self._seen:
                self._seen[client_id] = set()
            self._seen[client_id].add(request_id)
            self._dirty_count += 1
            if self._dirty_count >= TAMANIO_BATCH_PERSISTENCIA:
                self._persistir()
                self._dirty_count = 0

    def limpiar_cliente(self, client_id: str):
        with self._lock:
            if client_id in self._seen:
                del self._seen[client_id]
                self._persistir()
