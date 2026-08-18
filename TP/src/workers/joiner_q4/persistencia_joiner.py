import os

from common.persistencia import PersistidorEstado, VOLUMEN_DIR
from common.logger import obtener_logger
from common.constantes_protocolo import ID_CLIENTE
from base.constantes import CLAVE_BARRERA_COMPLETADA, CLAVE_IDS_PROCESADOS

logger = obtener_logger(__name__)

BASE_DIR = VOLUMEN_DIR

CLAVE_SCATTER = "scatter"
CLAVE_TXNS = "txns"


class PersistenciaJoiner:
    """
    Gestiona la persistencia del estado del join en disco.

    Cada cliente tiene su propia carpeta nombrada: <prefijo>_<client_id>.
    El scatter se serializa como dict de listas de listas (preserva orden).
    Las txns se serializan como dict de listas de listas (reconstruidas como set).
    """

    def __init__(self, prefijo_nodo: str, base_dir: str = BASE_DIR):
        self._prefijo = prefijo_nodo
        self._base_dir = base_dir

    def _nombre_carpeta(self, client_id: str) -> str:
        return f"{self._prefijo}_{client_id}"

    def guardar(self, client_id: str, scatter: dict, txns: dict, vistos: set):
        """Serializa y persiste el estado del cliente en disco."""
        scatter_serial = {k: [list(a) for a in v] for k, v in scatter.items()}
        txns_serial = {k: [list(c) for c in v] for k, v in txns.items()}
        PersistidorEstado(self._nombre_carpeta(client_id), base_dir=self._base_dir).guardar({
            ID_CLIENTE: client_id,
            CLAVE_SCATTER: scatter_serial,
            CLAVE_TXNS: txns_serial,
            CLAVE_IDS_PROCESADOS: list(vistos),
        })

    def recuperar_todos(self) -> dict[str, tuple[dict, dict, set]]:
        """
        Carga el estado de todos los clientes desde disco.

        Retorna un diccionario: client_id → (scatter, txns, vistos).
        Omite entradas con barrera completada (y las borra del disco).
        """
        if not os.path.exists(self._base_dir):
            logger.info(f"[PersistenciaJoiner] Directorio {self._base_dir} no existe. Arrancando limpio.")
            return {}

        carpetas = [c for c in os.listdir(self._base_dir) if c.startswith(self._prefijo + "_")]
        if not carpetas:
            logger.info("[PersistenciaJoiner] Sin estado previo en disco. Arrancando limpio.")
            return {}

        resultado = {}
        for carpeta in carpetas:
            client_id = carpeta[len(self._prefijo) + 1:]
            persistidor = PersistidorEstado(carpeta, base_dir=self._base_dir)
            estado = persistidor.cargar()

            if not estado:
                continue

            if estado.get(CLAVE_BARRERA_COMPLETADA, False):
                logger.info(f"[PersistenciaJoiner] Barrera completada detectada para client_id={client_id}. Omitiendo recuperación.")
                continue

            scatter = {k: [tuple(a) for a in v] for k, v in estado.get(CLAVE_SCATTER, {}).items()}
            txns = {k: set(tuple(c) for c in v) for k, v in estado.get(CLAVE_TXNS, {}).items()}
            vistos = set(estado.get(CLAVE_IDS_PROCESADOS, []))
            resultado[client_id] = (scatter, txns, vistos)

            logger.info(
                f"[PersistenciaJoiner] Recuperado estado para client_id={client_id}: "
                f"scatter_keys={len(scatter)}, txns_keys={len(txns)}, vistos={len(vistos)}"
            )

        return resultado

    def borrar(self, client_id: str):
        """Elimina el estado del cliente del disco."""
        PersistidorEstado(self._nombre_carpeta(client_id), base_dir=self._base_dir).borrar()

    def marcar_barrera_completada(self, client_id: str):
        """Marca en disco que la barrera fue completada para este cliente."""
        PersistidorEstado(self._nombre_carpeta(client_id), base_dir=self._base_dir).guardar({CLAVE_BARRERA_COMPLETADA: True})

    def esta_barrera_completada(self, client_id: str) -> bool:
        estado = PersistidorEstado(self._nombre_carpeta(client_id), base_dir=self._base_dir).cargar()
        return estado.get(CLAVE_BARRERA_COMPLETADA, False)
