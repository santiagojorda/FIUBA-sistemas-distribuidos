from base import WorkerBase
from base.constantes import CLAVE_BARRERA_COMPLETADA
from base.coordinacion.hooks import crear_hook_crash_despues_flush
from common.logger import Logger, obtener_logger
from common.persistencia import TAMANIO_BATCH_PERSISTENCIA
from common.constantes_protocolo import ID_SOLICITUD
from acumulador_joiner import AcumuladorJoiner
from persistencia_joiner import PersistenciaJoiner, BASE_DIR
from procesador_join import ProcesadorLotes
from emisor_join import EmisorResultados

logger = obtener_logger(__name__)


class JoinerQ4Worker(WorkerBase):
    """
    Gather-join para la query Q4.

    Recibe dos flujos indexados por el mismo campo (B):
      - aristas scatter : (A→B) donde A envió exactamente 5 destinos B distintos
      - transacciones   : todas las transacciones del período (para detectar B→C)

    Al recibir EOF de un cliente emite tripletas (A, B, C) que forman caminos
    del scatter-gather, descartando caminos degenerados (A=B, B=C, A=C).
    """

    TAMANIO_LOTE_GUARDADO = TAMANIO_BATCH_PERSISTENCIA

    def __init__(self):
        super().__init__()
        self.acumulador = AcumuladorJoiner()
        prefijo = f"joiner_q4_{self.configuracion.id_nodo}"
        self.persistencia = PersistenciaJoiner(prefijo, BASE_DIR)
        self.procesador = ProcesadorLotes(self.acumulador)
        self.emisor = EmisorResultados(self._enviar)
        self._hook_post_flush = crear_hook_crash_despues_flush()
        self._recuperar_estado()
        logger.info("[JoinerQ4] Iniciado.")

    def _recuperar_estado(self):
        """Restaura el estado de todos los clientes desde disco al iniciar."""
        datos = self.persistencia.recuperar_todos()
        for client_id, (scatter, txns, vistos) in datos.items():
            with self.acumulador.lock:
                self.acumulador.restaurar(client_id, scatter, txns, vistos)

    def procesar_payload(self, queue_name: str, client_id: str, payload: dict,
                         mensaje_original: bytes, ack, nack):
        acks_a_liberar = []
        try:
            with self.acumulador.lock:
                request_id = payload.get(ID_SOLICITUD)

                if request_id and self.acumulador.ya_visto(client_id, request_id):
                    logger.warning(f"[JoinerQ4] Duplicado ignorado: request_id={request_id} client_id={client_id}")
                    acks_a_liberar = [ack]
                else:
                    self.procesador.procesar_payload(payload, queue_name, client_id)
                    if request_id:
                        self.acumulador.marcar_visto(client_id, request_id)
                    self.acumulador.registrar_ack(client_id, ack)

                    if self.acumulador.total_acks_pendientes() >= self.TAMANIO_LOTE_GUARDADO:
                        clientes = self.acumulador.clientes_con_acks()
                        for cid in clientes:
                            self.persistencia.guardar(
                                cid,
                                self.acumulador.snapshot_scatter(cid),
                                self.acumulador.snapshot_txns(cid),
                                self.acumulador.snapshot_vistos(cid),
                            )
                        for cid in clientes:
                            acks_a_liberar.extend(self.acumulador.extraer_acks(cid))

        except Exception as e:
            logger.error(f"Error procesando payload: {e}", exc_info=True)
            nack()
            return

        for fn in acks_a_liberar:
            fn()

    def al_completar_eof_local(self, client_id: str):
        """Libera los acks del último lote parcial antes de que el coordinador
        espere vuelos=0. Si esperáramos a al_completar_cliente habría deadlock."""
        acks_a_liberar = []
        with self.acumulador.lock:
            self.persistencia.guardar(
                client_id,
                self.acumulador.snapshot_scatter(client_id),
                self.acumulador.snapshot_txns(client_id),
                self.acumulador.snapshot_vistos(client_id),
            )
            acks_a_liberar = self.acumulador.extraer_acks(client_id)
        for fn in acks_a_liberar:
            fn()

    def al_completar_cliente(self, client_id: str):
        """Emite resultados y limpia el estado del cliente al recibir EOF completo."""
        if self.persistencia.esta_barrera_completada(client_id):
            logger.info(f"[JoinerQ4] Flush ya completado para {client_id}, omitiendo re-emisión.")
            return

        with self.acumulador.lock:
            self.persistencia.guardar(
                client_id,
                self.acumulador.snapshot_scatter(client_id),
                self.acumulador.snapshot_txns(client_id),
                self.acumulador.snapshot_vistos(client_id),
            )
            scatter, txns = self.acumulador.extraer_cliente(client_id)

        enviados = self.emisor.emitir(client_id, scatter, txns)
        logger.info(f"[JoinerQ4] Flush completo para client_id={client_id}. Registros emitidos: {enviados}.")

        if self._hook_post_flush:
            self._hook_post_flush()

        self.persistencia.marcar_barrera_completada(client_id)

    def al_desconectar_cliente(self, client_id: str):
        """Descarta el estado del cliente sin emitir resultados."""
        acks_a_liberar = []
        with self.acumulador.lock:
            acks_a_liberar = self.acumulador.extraer_acks(client_id)
            self.acumulador.extraer_cliente(client_id)
        self.persistencia.borrar(client_id)
        for fn in acks_a_liberar:
            fn()
        logger.info(f"[JoinerQ4] Estado descartado para client_id={client_id}.")

    def al_cerrar(self):
        logger.info("[JoinerQ4] Apagado.")


def main():
    Logger.configurar("joiner_q4")
    JoinerQ4Worker().iniciar()


if __name__ == "__main__":
    main()
