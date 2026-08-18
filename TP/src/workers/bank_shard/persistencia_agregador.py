import os
from common.logger import obtener_logger
from common.persistencia import PersistidorEstado
from constantes import (
    CLAVE_TX_EOF_COUNT, CLAVE_BANK_EOF_COUNT,
    CLAVE_EOF_MENSAJE, CLAVE_EOF_MENSAJE_HEX,
    CLAVE_FLUSH_INICIADO, CLAVE_BARRERA_COMPLETADA, CLAVE_BANCOS,
    CLAVE_IDS_PROCESADOS,
)
from common.constantes_protocolo import ID_CLIENTE

logger = obtener_logger(__name__)


def serializar_estado(client_id: str, datos_bancos: dict,
                      estado_eof: dict, ids_procesados: set) -> dict:
    eof_msg = estado_eof.get(CLAVE_EOF_MENSAJE)
    return {
        ID_CLIENTE: client_id,
        CLAVE_TX_EOF_COUNT: estado_eof.get(CLAVE_TX_EOF_COUNT, 0),
        CLAVE_BANK_EOF_COUNT: estado_eof.get(CLAVE_BANK_EOF_COUNT, 0),
        CLAVE_EOF_MENSAJE_HEX: eof_msg.hex() if eof_msg else None,
        CLAVE_FLUSH_INICIADO: estado_eof.get(CLAVE_FLUSH_INICIADO, False),
        CLAVE_BARRERA_COMPLETADA: estado_eof.get(CLAVE_BARRERA_COMPLETADA, False),
        "eofs_recibidos": estado_eof.get("eofs_recibidos", []),
        CLAVE_BANCOS: datos_bancos,
        CLAVE_IDS_PROCESADOS: list(ids_procesados),
    }


class PersistenciaAgregador:

    def __init__(self, prefijo_nodo: str, base_dir: str):
        self._prefijo = prefijo_nodo
        self._base_dir = base_dir

    def _persistidor(self, client_id: str) -> PersistidorEstado:
        return PersistidorEstado(f"{self._prefijo}_{client_id}", base_dir=self._base_dir)

    def recuperar_estados(self) -> dict[str, dict]:
        resultado: dict[str, dict] = {}

        if not os.path.exists(self._base_dir):
            return resultado

        prefijo = f"{self._prefijo}_"
        for carpeta in os.listdir(self._base_dir):
            if not carpeta.startswith(prefijo):
                continue
            if not os.path.isdir(os.path.join(self._base_dir, carpeta)):
                continue

            client_id = carpeta[len(prefijo):]
            persistidor = self._persistidor(client_id)
            estado = persistidor.cargar()

            if not estado:
                continue

            if estado.get(CLAVE_BARRERA_COMPLETADA, False):
                persistidor.borrar()
                logger.info(f"Barrera completada para client_id={client_id}. Limpiando remanente.")
                continue

            resultado[client_id] = estado

        return resultado

    def guardar(self, client_id: str, datos_bancos: dict,
                estado_eof: dict, ids_procesados: set):
        estado = serializar_estado(client_id, datos_bancos, estado_eof, ids_procesados)
        self._persistidor(client_id).guardar(estado)

    def marcar_completado(self, client_id: str, datos_bancos: dict,
                          estado_eof: dict, ids_procesados: set):
        estado_eof[CLAVE_BARRERA_COMPLETADA] = True
        estado = serializar_estado(client_id, datos_bancos, estado_eof, ids_procesados)
        self._persistidor(client_id).guardar(estado)

    def borrar(self, client_id: str):
        self._persistidor(client_id).borrar()

    @property
    def base_dir(self) -> str:
        return self._base_dir
