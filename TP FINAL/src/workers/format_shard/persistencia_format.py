import os
from common.message_protocol.internal import ParseadorMensajes
from common.logger import obtener_logger
from common.persistencia import PersistidorEstado
from constantes import (
    CLAVE_TEMPRANO_CERRADO, CLAVE_TARDIO_CERRADO, CLAVE_PROMEDIOS_LISTOS,
    CLAVE_PROMEDIOS, CLAVE_DATOS_TEMPRANO, CLAVE_EOF_MENSAJE,
    CLAVE_EOF_MENSAJE_HEX, CLAVE_CACHE_PROCESADO, CLAVE_BARRERA_COMPLETADA,
    CLAVE_IDS_PROCESADOS, CLAVE_CACHE_SOLICITUD, CLAVE_CACHE_ESQUEMA,
    CLAVE_CACHE_REGISTROS,
)

logger = obtener_logger(__name__)


def serializar_estado(id_cliente: str, estado: dict) -> dict:
    eof_msg = estado.get(CLAVE_EOF_MENSAJE)
    return {
        "client_id": id_cliente,
        CLAVE_TEMPRANO_CERRADO: estado[CLAVE_TEMPRANO_CERRADO],
        CLAVE_TARDIO_CERRADO: estado[CLAVE_TARDIO_CERRADO],
        CLAVE_PROMEDIOS_LISTOS: estado[CLAVE_PROMEDIOS_LISTOS],
        CLAVE_PROMEDIOS: estado[CLAVE_PROMEDIOS],
        CLAVE_DATOS_TEMPRANO: estado[CLAVE_DATOS_TEMPRANO],
        CLAVE_EOF_MENSAJE_HEX: eof_msg.hex() if eof_msg else None,
        CLAVE_CACHE_PROCESADO: estado[CLAVE_CACHE_PROCESADO],
        CLAVE_BARRERA_COMPLETADA: estado.get(CLAVE_BARRERA_COMPLETADA, False),
        CLAVE_IDS_PROCESADOS: list(estado[CLAVE_IDS_PROCESADOS]),
    }


class PersistenciaFormateador:

    def __init__(self, prefijo_nodo: str, dir_base: str):
        self._prefijo = prefijo_nodo
        self._dir_base = dir_base

    def _persistidor(self, id_cliente: str) -> PersistidorEstado:
        return PersistidorEstado(f"{self._prefijo}_{id_cliente}", base_dir=self._dir_base)

    def _obtener_ruta_cache(self, id_cliente: str) -> str:
        nombre = f"{self._prefijo}_{id_cliente}"
        directorio = os.path.join(self._dir_base, nombre)
        os.makedirs(directorio, exist_ok=True)
        return os.path.join(directorio, "cache_tardio.jsonl")

    def escribir_en_cache(self, id_cliente: str, id_solicitud: str, esquema: list, registros: list):
        ruta = self._obtener_ruta_cache(id_cliente)
        linea = ParseadorMensajes.serializar({
            CLAVE_CACHE_SOLICITUD: id_solicitud,
            CLAVE_CACHE_ESQUEMA: esquema,
            CLAVE_CACHE_REGISTROS: registros
        }).decode("utf-8")
        with open(ruta, "a+b") as f:
            tamanio = f.seek(0, 2)
            if tamanio > 0:
                f.seek(-1, 2)
                if f.read(1) != b'\n':
                    f.write(b'\n')
            f.write((linea + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    def recuperar_estados(self) -> dict[str, dict]:
        resultado: dict[str, dict] = {}

        if not os.path.exists(self._dir_base):
            return resultado

        prefijo = f"{self._prefijo}_"
        for folder_name in os.listdir(self._dir_base):
            if not folder_name.startswith(prefijo):
                continue
            if not os.path.isdir(os.path.join(self._dir_base, folder_name)):
                continue

            id_cliente = folder_name[len(prefijo):]
            persistidor = self._persistidor(id_cliente)
            saved = persistidor.cargar()
            ruta_cache = self._obtener_ruta_cache(id_cliente)

            if not saved and not os.path.exists(ruta_cache):
                continue

            saved = saved or {}
            eof_hex = saved.get(CLAVE_EOF_MENSAJE_HEX)
            barrier_completada = saved.get(CLAVE_BARRERA_COMPLETADA, False)

            estado = {
                CLAVE_TEMPRANO_CERRADO: saved.get(CLAVE_TEMPRANO_CERRADO, False),
                CLAVE_TARDIO_CERRADO: saved.get(CLAVE_TARDIO_CERRADO, False),
                CLAVE_PROMEDIOS_LISTOS: saved.get(CLAVE_PROMEDIOS_LISTOS, False),
                CLAVE_PROMEDIOS: saved.get(CLAVE_PROMEDIOS, {}),
                CLAVE_DATOS_TEMPRANO: saved.get(CLAVE_DATOS_TEMPRANO, {}),
                CLAVE_EOF_MENSAJE: bytes.fromhex(eof_hex) if eof_hex else None,
                CLAVE_CACHE_PROCESADO: saved.get(CLAVE_CACHE_PROCESADO, False),
                CLAVE_BARRERA_COMPLETADA: barrier_completada,
                CLAVE_IDS_PROCESADOS: set(saved.get(CLAVE_IDS_PROCESADOS, [])),
            }

            if os.path.exists(ruta_cache):
                with open(ruta_cache, "r", encoding="utf-8") as f:
                    for linea in f:
                        linea = linea.strip()
                        if not linea:
                            continue
                        try:
                            entry = ParseadorMensajes.deserializar(linea)
                            rid = entry.get(CLAVE_CACHE_SOLICITUD)
                            if rid:
                                estado[CLAVE_IDS_PROCESADOS].add(rid)
                        except Exception:
                            pass


            if estado[CLAVE_TEMPRANO_CERRADO] and estado[CLAVE_TARDIO_CERRADO] and estado[CLAVE_CACHE_PROCESADO] and barrier_completada:
                persistidor.borrar()
                self.borrar_archivo_cache(id_cliente)
                logger.info(f"[Recuperación] Cliente {id_cliente}: barrera ya completada, limpiando remanente.")
                continue

            resultado[id_cliente] = estado

        return resultado

    def guardar(self, id_cliente: str, estado: dict):
        self._persistidor(id_cliente).guardar(serializar_estado(id_cliente, estado))

    def marcar_completado(self, id_cliente: str, estado: dict):
        estado[CLAVE_BARRERA_COMPLETADA] = True
        self.guardar(id_cliente, estado)

    def borrar(self, id_cliente: str):
        self._persistidor(id_cliente).borrar()

    def borrar_archivo_cache(self, id_cliente: str):
        ruta_cache = self._obtener_ruta_cache(id_cliente)
        if os.path.exists(ruta_cache):
            try:
                os.remove(ruta_cache)
            except Exception as e:
                logger.warning(f"[Persistencia] No se pudo eliminar cache file para {id_cliente}: {e}")
