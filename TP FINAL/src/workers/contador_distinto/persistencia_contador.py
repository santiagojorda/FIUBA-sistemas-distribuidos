import json
import os

from common.persistencia import PersistidorEstado, VOLUMEN_DIR
from common.logger import obtener_logger
from common.constantes_protocolo import ID_CLIENTE
from base.constantes import CLAVE_BARRERA_COMPLETADA, CLAVE_IDS_PROCESADOS

logger = obtener_logger(__name__)

BASE_DIR = VOLUMEN_DIR

CLAVE_GRUPOS = "grupos"


class PersistenciaContador:
    """
    Gestiona la persistencia del estado del contador en disco.

    Cada cliente tiene su propia carpeta nombrada: <prefijo>_<client_id>.
    El estado se serializa como JSON con los grupos y los request_ids vistos.
    """

    def __init__(self, prefijo_nodo: str, base_dir: str = BASE_DIR):
        self._prefijo = prefijo_nodo
        self._base_dir = base_dir

    def _nombre_carpeta(self, client_id: str) -> str:
        return f"{self._prefijo}_{client_id}"

    def guardar(self, client_id: str, grupos: dict, vistos: set):
        """Serializa y persiste el estado del cliente en disco."""
        grupos_serial = {}
        for clave_grupo, conjunto_valores in grupos.items():
            k = json.dumps(list(clave_grupo))
            grupos_serial[k] = [list(v) for v in conjunto_valores]

        PersistidorEstado(self._nombre_carpeta(client_id), base_dir=self._base_dir).guardar({
            ID_CLIENTE: client_id,
            CLAVE_GRUPOS: grupos_serial,
            CLAVE_IDS_PROCESADOS: list(vistos),
        })

    def recuperar_todos(self) -> dict[str, tuple[dict, set]]:
        """
        Carga el estado de todos los clientes desde disco.

        Retorna un diccionario: client_id → (grupos, vistos).
        Omite entradas con barrera completada (y las borra del disco).
        """
        if not os.path.exists(self._base_dir):
            logger.info(f"[PersistenciaContador] Directorio {self._base_dir} no existe. Arrancando limpio.")
            return {}

        carpetas = [c for c in os.listdir(self._base_dir) if c.startswith(self._prefijo + "_")]
        if not carpetas:
            logger.info("[PersistenciaContador] Sin estado previo en disco. Arrancando limpio.")
            return {}

        resultado = {}
        for carpeta in carpetas:
            client_id = carpeta[len(self._prefijo) + 1:]
            persistidor = PersistidorEstado(carpeta, base_dir=self._base_dir)
            estado = persistidor.cargar()

            if not estado:
                continue

            if estado.get(CLAVE_BARRERA_COMPLETADA, False):
                logger.info(f"[PersistenciaContador] Barrera completada detectada para client_id={client_id}. Omitiendo recuperación.")
                continue

            grupos_serial = estado.get(CLAVE_GRUPOS, {})
            grupos = {}
            for k, vlist in grupos_serial.items():
                clave_grupo = tuple(json.loads(k))
                grupos[clave_grupo] = set(tuple(v) for v in vlist)

            vistos = set(estado.get(CLAVE_IDS_PROCESADOS, []))
            resultado[client_id] = (grupos, vistos)

            logger.info(
                f"[PersistenciaContador] Recuperado estado para client_id={client_id}: "
                f"grupos={len(grupos)}, vistos={len(vistos)}"
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
