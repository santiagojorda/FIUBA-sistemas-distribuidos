from base.worker_base import WorkerBase
from common.logger import Logger, obtener_logger
from common.constantes_protocolo import ID_CLIENTE, LOTES, CABECERA, ESQUEMA, CANTIDAD, PAYLOAD, ID_SOLICITUD
from common.message_protocol.internal import ParseadorMensajes
from estado_conteo import EstadoConteo, calcular_cantidad
from base.coordinacion.hooks import crear_hook_crash_despues_persistir, crear_hook_crash_despues_flush

logger = obtener_logger(__name__)


def construir_resultado_conteo(client_id: str, conteo: int) -> dict:
    return {
        ID_CLIENTE: client_id,
        LOTES: [
            {
                CABECERA: {
                    ESQUEMA: [CANTIDAD],
                    ID_CLIENTE: client_id,
                    CANTIDAD: 1,
                },
                PAYLOAD: [[conteo]],
            }
        ],
    }


class CounterWorker(WorkerBase):

    def __init__(self):
        super().__init__()
        self.estado = EstadoConteo(self.configuracion.id_nodo)
        self._hook_post_persistir = crear_hook_crash_despues_persistir()
        self._hook_post_flush = crear_hook_crash_despues_flush()

    def procesar_payload(self, nombre_cola: str, client_id: str, payload: dict,
                         mensaje_original: bytes, ack, nack):
        try:
            request_id = payload.get(ID_SOLICITUD)
            cantidad = calcular_cantidad(payload)
            ya_procesado = self.estado.incrementar(client_id, cantidad, request_id)

            if ya_procesado:
                logger.info(f"Mensaje duplicado detectado localmente por persistencia: request_id={request_id}")
                ack()
                return

            if self._hook_post_persistir:
                self._hook_post_persistir()

            ack()
        except Exception as e:
            logger.error(f"Error contando mensaje: {e}", exc_info=True)
            nack()

    def al_completar_cliente(self, client_id: str):
        if self.estado.ya_completado(client_id):
            logger.info(f"Flush ya completado para {client_id}, omitiendo re-emisión.")
            return

        conteo = self.estado.obtener_y_limpiar(client_id)
        resultado = construir_resultado_conteo(client_id, conteo)
        self._enviar(ParseadorMensajes.serializar(resultado), payload=resultado)
        logger.info(f"Conteo emitido para {client_id}: {conteo} transacciones.")

        if self._hook_post_flush:
            self._hook_post_flush()

        self.estado.marcar_completado(client_id)

    def al_desconectar_cliente(self, client_id: str):
        self.estado.descartar(client_id)
        logger.info(f"Estado descartado para {client_id}.")

    def al_cerrar(self):
        logger.info("Counter apagado.")


def main():
    Logger.configurar("counter")
    CounterWorker().iniciar()


if __name__ == "__main__":
    main()
