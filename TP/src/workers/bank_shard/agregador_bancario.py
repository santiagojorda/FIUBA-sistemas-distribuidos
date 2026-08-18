import threading
from base.worker_base import WorkerBase
from base.coordinacion.hooks import crear_hook_crash_pre_barrera
from common.logger import Logger, obtener_logger
from common.constantes_protocolo import CABECERA, ESQUEMA, PAYLOAD, LOTES, ID_SOLICITUD
from common.message_protocol.internal import ParseadorMensajes
from config_agregador import ConfigAgregador
from procesador_registros import ProcesadorRegistros
from persistencia_agregador import PersistenciaAgregador
from formateador_salida import construir_resultado
from constantes import (
    CLAVE_TX_EOF_COUNT, CLAVE_BANK_EOF_COUNT, CLAVE_FLUSH_INICIADO,
    CLAVE_BARRERA_COMPLETADA, CLAVE_BANCOS, CLAVE_IDS_PROCESADOS,
    CLAVE_EOF_MENSAJE, CLAVE_EOF_MENSAJE_HEX,
    COLA_TRANSACCIONES, COLA_BANCOS,
    INTERVALO_PERSISTENCIA, PREFIJO_BANK_SHARD,
)

logger = obtener_logger(__name__)


def _crear_estado_eof_vacio() -> dict:
    return {
        CLAVE_TX_EOF_COUNT: 0,
        CLAVE_BANK_EOF_COUNT: 0,
        CLAVE_EOF_MENSAJE: None,
        CLAVE_FLUSH_INICIADO: False,
        CLAVE_BARRERA_COMPLETADA: False,
        "eofs_recibidos": [],
    }


class AgregadorBancarioWorker(WorkerBase):

    def __init__(self):
        super().__init__()
        self._config = ConfigAgregador(self.configuracion.id_nodo)
        self._procesador = ProcesadorRegistros()
        self._persistencia = PersistenciaAgregador(
            self._config.prefijo_nodo, self._config.base_dir
        )

        self._datos_bancos: dict[str, dict] = {}
        self._estado_eof: dict[str, dict] = {}
        self._ids_procesados: dict[str, set] = {}
        self._acks_pendientes: dict[str, list] = {}
        self._mensajes_desde_flush: dict[str, int] = {}

        self._locks_cliente: dict[str, threading.Lock] = {}
        self._lock_global = threading.Lock()

        self._barreras_para_iniciar: list[tuple[str, bytes]] = []

        self._hook_pre_barrera = crear_hook_crash_pre_barrera(self._config.prefijo_nodo)

        self._recuperar_estado()
        logger.info("AgregadorBancario inicializado.")

    # ── Locks por cliente ──

    def _obtener_lock(self, client_id: str) -> threading.Lock:
        with self._lock_global:
            if client_id not in self._locks_cliente:
                self._locks_cliente[client_id] = threading.Lock()
            return self._locks_cliente[client_id]

    def _liberar_lock(self, client_id: str):
        with self._lock_global:
            self._locks_cliente.pop(client_id, None)

    # ── Persistencia por lotes ──

    def _persistir_estado(self, client_id: str):
        self._persistencia.guardar(
            client_id,
            self._datos_bancos.get(client_id, {}),
            self._estado_eof.get(client_id, {}),
            self._ids_procesados.get(client_id, set()),
        )

    def _flush_acks_pendientes(self, client_id: str):
        for ack_pendiente in self._acks_pendientes.get(client_id, []):
            ack_pendiente()
        self._acks_pendientes.pop(client_id, None)

    # ── Recuperación ──

    def _recuperar_estado(self):
        estados = self._persistencia.recuperar_estados()

        for client_id, estado in estados.items():
            tx_eof = estado.get(CLAVE_TX_EOF_COUNT, 0)
            bank_eof = estado.get(CLAVE_BANK_EOF_COUNT, 0)
            eof_hex = estado.get(CLAVE_EOF_MENSAJE_HEX)

            tx_cerrado = tx_eof >= self._config.total_tx_upstream
            bancos_cerrado = bank_eof >= self._config.total_bank_upstream

            with self._obtener_lock(client_id):
                self._datos_bancos[client_id] = estado.get(CLAVE_BANCOS, {})
                self._ids_procesados[client_id] = set(estado.get(CLAVE_IDS_PROCESADOS, []))
                self._estado_eof[client_id] = {
                    CLAVE_TX_EOF_COUNT: tx_eof,
                    CLAVE_BANK_EOF_COUNT: bank_eof,
                    CLAVE_EOF_MENSAJE: bytes.fromhex(eof_hex) if eof_hex else None,
                    CLAVE_FLUSH_INICIADO: estado.get(CLAVE_FLUSH_INICIADO, False),
                    CLAVE_BARRERA_COMPLETADA: False,
                    "eofs_recibidos": estado.get("eofs_recibidos", []),
                }

                if tx_cerrado and bancos_cerrado:
                    self._estado_eof[client_id][CLAVE_FLUSH_INICIADO] = True
                    self.coordinador.marcar_eof_local_completo(client_id)
                    self._barreras_para_iniciar.append(
                        (client_id, self._estado_eof[client_id][CLAVE_EOF_MENSAJE])
                    )
                    logger.info(f"[Recuperación] {client_id}: barrera pendiente, se iniciará al arrancar.")
                else:
                    logger.info(
                        f"[Recuperación] Estado parcial para {client_id} "
                        f"(tx={tx_eof}/{self._config.total_tx_upstream}, "
                        f"bank={bank_eof}/{self._config.total_bank_upstream})."
                    )

    # ── Procesamiento de datos ──

    def procesar_payload(self, nombre_cola: str, client_id: str, payload: dict,
                         mensaje_original: bytes, ack, nack):
        try:
            request_id = payload.get(ID_SOLICITUD)
            lock = self._obtener_lock(client_id)

            with lock:
                if request_id and request_id in self._ids_procesados.get(client_id, set()):
                    logger.info(f"Duplicado propio descartado request_id={request_id} client_id={client_id}.")
                    ack()
                    return

                if client_id not in self._datos_bancos:
                    self._datos_bancos[client_id] = {}

                self._procesar_registros(nombre_cola, client_id, payload)

                if request_id:
                    self._ids_procesados.setdefault(client_id, set()).add(request_id)

                self._acks_pendientes.setdefault(client_id, []).append(ack)
                self._mensajes_desde_flush[client_id] = self._mensajes_desde_flush.get(client_id, 0) + 1

                if self._mensajes_desde_flush[client_id] >= INTERVALO_PERSISTENCIA:
                    self._mensajes_desde_flush[client_id] = 0
                    self._persistir_estado(client_id)
                    self._flush_acks_pendientes(client_id)

        except ValueError as e:
            logger.error(f"Error de conversión numérica para {client_id}: {e}")
            nack()
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}", exc_info=True)
            nack()

    def _procesar_registros(self, nombre_cola: str, client_id: str, payload: dict):
        estado = self._datos_bancos[client_id]

        if LOTES in payload:
            for lote in payload[LOTES]:
                esquema = lote[CABECERA][ESQUEMA]
                registros = lote[PAYLOAD]
                if COLA_TRANSACCIONES in nombre_cola:
                    self._procesador.procesar_transacciones(estado, esquema, registros)
                elif COLA_BANCOS in nombre_cola:
                    self._procesador.procesar_bancos(estado, esquema, registros)
        else:
            if COLA_TRANSACCIONES in nombre_cola:
                self._procesador.procesar_transaccion_individual(estado, payload)
            elif COLA_BANCOS in nombre_cola:
                self._procesador.procesar_banco_individual(estado, payload)

    # ── Coordinación EOF ──

    def interceptar_eof(self, nombre_cola: str, client_id: str, payload: dict,
                        mensaje_original: bytes) -> bool:
        iniciar_barrera = False
        mensaje_barrera = None
        lock = self._obtener_lock(client_id)
        request_id = payload.get(ID_SOLICITUD)

        with lock:
            if client_id not in self._estado_eof:
                self._estado_eof[client_id] = _crear_estado_eof_vacio()

            estado = self._estado_eof[client_id]

            if request_id:
                procesados = estado.setdefault("eofs_recibidos", [])
                if request_id in procesados:
                    logger.info(f"EOF duplicado interceptado para {client_id}: {request_id}")
                    return True
                procesados.append(request_id)

            if not estado[CLAVE_EOF_MENSAJE]:
                estado[CLAVE_EOF_MENSAJE] = mensaje_original

            if COLA_TRANSACCIONES in nombre_cola:
                estado[CLAVE_TX_EOF_COUNT] += 1
                logger.info(
                    f"EOF Transacciones para {client_id} "
                    f"({estado[CLAVE_TX_EOF_COUNT]}/{self._config.total_tx_upstream})."
                )
            elif COLA_BANCOS in nombre_cola:
                estado[CLAVE_BANK_EOF_COUNT] += 1
                logger.info(
                    f"EOF Bancos para {client_id} "
                    f"({estado[CLAVE_BANK_EOF_COUNT]}/{self._config.total_bank_upstream})."
                )

            tx_cerrado = estado[CLAVE_TX_EOF_COUNT] >= self._config.total_tx_upstream
            bancos_cerrado = estado[CLAVE_BANK_EOF_COUNT] >= self._config.total_bank_upstream

            self._persistir_estado(client_id)
            self._flush_acks_pendientes(client_id)

            if tx_cerrado and bancos_cerrado and not estado[CLAVE_FLUSH_INICIADO]:
                logger.info(f"Ambas colas cerradas para {client_id}. Solicitando barrera.")

                if self._hook_pre_barrera:
                    self._hook_pre_barrera()

                estado[CLAVE_FLUSH_INICIADO] = True
                self._persistir_estado(client_id)

                iniciar_barrera = True
                mensaje_barrera = estado[CLAVE_EOF_MENSAJE]

        if iniciar_barrera:
            self.coordinador.iniciar_barrera(client_id, mensaje_barrera)

        return True

    def al_iniciar_post_arranque(self):
        for client_id, eof_mensaje in self._barreras_para_iniciar:
            logger.info(f"Iniciando barrera diferida para {client_id} post-recovery.")
            self.coordinador.iniciar_barrera(client_id, eof_mensaje)
        self._barreras_para_iniciar.clear()

    # ── Completar / Desconectar ──

    def al_completar_cliente(self, client_id: str):
        lock = self._obtener_lock(client_id)
        with lock:
            datos = self._datos_bancos.get(client_id)
            if datos:
                resultado = construir_resultado(client_id, datos)
                if resultado:
                    self._hilo_local.id_solicitud_actual = (
                        f"{PREFIJO_BANK_SHARD}_output:{client_id}:{self.configuracion.id_nodo}"
                    )
                    try:
                        self._enviar(ParseadorMensajes.serializar(resultado), payload=resultado)
                    finally:
                        self._hilo_local.id_solicitud_actual = None

                logger.info(f"Envío finalizado para {client_id}.")
                del self._datos_bancos[client_id]
            else:
                logger.warning(f"al_completar_cliente para {client_id} sin datos locales.")

            if client_id in self._estado_eof:
                self._persistencia.marcar_completado(
                    client_id,
                    self._datos_bancos.get(client_id, {}),
                    self._estado_eof[client_id],
                    self._ids_procesados.get(client_id, set()),
                )

            self._estado_eof.pop(client_id, None)
            self._ids_procesados.pop(client_id, None)
            self._mensajes_desde_flush.pop(client_id, None)
            self._acks_pendientes.pop(client_id, None)

            self._persistencia.borrar(client_id)

        self._liberar_lock(client_id)

    def al_desconectar_cliente(self, client_id: str):
        lock = self._obtener_lock(client_id)
        with lock:
            self._datos_bancos.pop(client_id, None)
            self._estado_eof.pop(client_id, None)
            self._ids_procesados.pop(client_id, None)
            self._mensajes_desde_flush.pop(client_id, None)
            self._acks_pendientes.pop(client_id, None)
            self._persistencia.borrar(client_id)
        self._liberar_lock(client_id)

    def al_cerrar(self):
        logger.info("AgregadorBancario apagado.")


def main():
    Logger.configurar("bank_shard")
    AgregadorBancarioWorker().iniciar()


if __name__ == "__main__":
    main()
