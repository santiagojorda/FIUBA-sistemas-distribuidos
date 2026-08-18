import threading
import os
from base import WorkerBase
from common.logger import Logger, obtener_logger
from common.message_protocol.internal import ParseadorMensajes
from common.constantes_protocolo import ID_SOLICITUD, LOTES, CABECERA, ESQUEMA, PAYLOAD
from config_format import ConfigFormateador
from persistencia_format import PersistenciaFormateador
from procesador_registros import ProcesadorRegistros
from constantes import (
    CLAVE_TEMPRANO_CERRADO, CLAVE_TARDIO_CERRADO, CLAVE_PROMEDIOS_LISTOS,
    CLAVE_PROMEDIOS, CLAVE_DATOS_TEMPRANO, CLAVE_EOF_MENSAJE,
    CLAVE_CACHE_PROCESADO, CLAVE_BARRERA_COMPLETADA, CLAVE_IDS_PROCESADOS,
    COLA_TEMPRANO, COLA_TARDIO,
)

logger = obtener_logger(__name__)


class FormateadorShardWorker(WorkerBase):

    def __init__(self):
        super().__init__()
        self._config = ConfigFormateador(self.configuracion.id_nodo)
        self._persistencia = PersistenciaFormateador(self._config.prefijo_nodo, self._config.base_dir)
        self._procesador = ProcesadorRegistros()

        self.estado_clientes = {}
        self.lock = threading.Lock()
        self._barreras_para_iniciar = []

        self._recuperar_estado()
        logger.info("[FormatShard] Worker inicializado.")

    def _recuperar_estado(self):
        estados = self._persistencia.recuperar_estados()
        for id_cliente, estado in estados.items():
            self.estado_clientes[id_cliente] = estado
            if estado[CLAVE_TEMPRANO_CERRADO] and estado[CLAVE_TARDIO_CERRADO] and estado[CLAVE_CACHE_PROCESADO]:
                self.coordinador.marcar_eof_local_completo(id_cliente)
                self._barreras_para_iniciar.append((id_cliente, estado[CLAVE_EOF_MENSAJE]))
                logger.info(f"[Recuperación] Cliente {id_cliente}: barrera pendiente, se iniciará al arrancar.")
            else:
                logger.info(f"[Recuperación] Estado parcial cargado para cliente {id_cliente}.")

    def _obtener_estado(self, id_cliente: str) -> dict:
        if id_cliente not in self.estado_clientes:
            self.estado_clientes[id_cliente] = {
                CLAVE_TEMPRANO_CERRADO: False,
                CLAVE_TARDIO_CERRADO: False,
                CLAVE_PROMEDIOS_LISTOS: False,
                CLAVE_PROMEDIOS: {},
                CLAVE_DATOS_TEMPRANO: {},
                CLAVE_EOF_MENSAJE: None,
                CLAVE_CACHE_PROCESADO: False,
                CLAVE_BARRERA_COMPLETADA: False,
                CLAVE_IDS_PROCESADOS: set(),
            }
        return self.estado_clientes[id_cliente]

    def procesar_payload(self, nombre_cola: str, id_cliente: str, datos: dict, mensaje_original: bytes, ack, nack):
        try:
            id_solicitud = datos.get(ID_SOLICITUD)

            with self.lock:
                estado = self._obtener_estado(id_cliente)

                if id_solicitud and id_solicitud in estado[CLAVE_IDS_PROCESADOS]:
                    ack()
                    return

                if LOTES in datos:
                    for batch in datos[LOTES]:
                        header = batch[CABECERA]
                        esquema = header[ESQUEMA]
                        registros = batch[PAYLOAD]

                        if COLA_TEMPRANO in nombre_cola:
                            self._procesador.acumular_temprano(estado, esquema, registros)
                        elif COLA_TARDIO in nombre_cola:
                            self._persistencia.escribir_en_cache(id_cliente, id_solicitud, esquema, registros)
                else:
                    if COLA_TEMPRANO in nombre_cola:
                        self._procesador.acumular_temprano_individual(estado, datos)
                    elif COLA_TARDIO in nombre_cola:
                        esquema = list(datos.keys())
                        valores_registro = list(datos.values())
                        self._persistencia.escribir_en_cache(id_cliente, id_solicitud, esquema, [valores_registro])

                if id_solicitud:
                    estado[CLAVE_IDS_PROCESADOS].add(id_solicitud)
                self._persistencia.guardar(id_cliente, estado)

            ack()

        except Exception as e:
            logger.error(f"Error procesando mensaje en {nombre_cola}: {e}", exc_info=True)
            nack()

    def interceptar_eof(self, nombre_cola: str, id_cliente: str, datos: dict, mensaje_original: bytes) -> bool:
        disparar_flush = False

        with self.lock:
            estado = self._obtener_estado(id_cliente)

            if not estado[CLAVE_EOF_MENSAJE]:
                estado[CLAVE_EOF_MENSAJE] = mensaje_original

            if COLA_TEMPRANO in nombre_cola:
                logger.info(f"EOF Temprano recibido para {id_cliente}.")
                estado[CLAVE_TEMPRANO_CERRADO] = True
                self._procesador.calcular_promedios(estado)
            elif COLA_TARDIO in nombre_cola:
                logger.info(f"EOF Tardío recibido para {id_cliente}.")
                estado[CLAVE_TARDIO_CERRADO] = True

            self._persistencia.guardar(id_cliente, estado)

            if estado[CLAVE_TEMPRANO_CERRADO] and estado[CLAVE_TARDIO_CERRADO] and not estado[CLAVE_CACHE_PROCESADO]:
                ruta_cache = self._persistencia._obtener_ruta_cache(id_cliente)
                tamanio_cache = os.path.getsize(ruta_cache) if os.path.exists(ruta_cache) else 0
                logger.info(f"Ambas fases cerradas para {id_cliente}. Procesando caché tardío ({tamanio_cache} bytes).")

                id_solicitud_salida = f"format_shard_output:{id_cliente}:{self.configuracion.id_nodo}"
                self._hilo_local.id_solicitud_actual = id_solicitud_salida
                try:
                    self._procesar_cache_tardio(id_cliente, estado)
                finally:
                    self._hilo_local.id_solicitud_actual = None

                estado[CLAVE_CACHE_PROCESADO] = True
                self._persistencia.guardar(id_cliente, estado)

                self.coordinador.marcar_eof_local_completo(id_cliente)

                disparar_flush = True

        if disparar_flush:
            logger.info(f"Caché procesado. Iniciando barrera distribuida para {id_cliente}.")
            self.coordinador.iniciar_barrera(id_cliente, estado[CLAVE_EOF_MENSAJE])

        return True

    def _procesar_cache_tardio(self, id_cliente: str, estado: dict):
        ruta_cache = self._persistencia._obtener_ruta_cache(id_cliente)
        registros = self._procesador.filtrar_registros_tardios(estado, ruta_cache)

        from formateador_salida import construir_resultado
        resultado = construir_resultado(id_cliente, registros)
        if resultado:
            self._enviar(ParseadorMensajes.serializar(resultado), payload=resultado)

        self._persistencia.borrar_archivo_cache(id_cliente)


    def al_completar_cliente(self, id_cliente: str):
        with self.lock:
            estado = self.estado_clientes.get(id_cliente)
            if estado:
                logger.info(f"Limpiando estado en memoria para {id_cliente}.")
                self._persistencia.marcar_completado(id_cliente, estado)
                self.estado_clientes.pop(id_cliente, None)
        self._persistencia.borrar(id_cliente)
        self._persistencia.borrar_archivo_cache(id_cliente)

    def al_iniciar_post_arranque(self):
        for id_cliente, eof_mensaje in self._barreras_para_iniciar:
            logger.info(f"Iniciando barrera diferida para {id_cliente} post-recovery.")
            self.coordinador.iniciar_barrera(id_cliente, eof_mensaje)
        self._barreras_para_iniciar.clear()

    def al_desconectar_cliente(self, id_cliente: str):
        with self.lock:
            self.estado_clientes.pop(id_cliente, None)
        self._persistencia.borrar(id_cliente)
        self._persistencia.borrar_archivo_cache(id_cliente)

    def al_cerrar(self):
        logger.info("Apagado exitoso.")


def main():
    Logger.configurar("format_shard")
    FormateadorShardWorker().iniciar()


if __name__ == "__main__":
    main()
