from base.worker_base import WorkerBase
from common.logger import Logger, obtener_logger
from config_filtro import ConfigFiltro
from procesador_lotes import ProcesadorLotes
from reglas import FabricaReglas
from common.constantes_protocolo import FIN_DE_ARCHIVO, LOTES
from common.message_protocol.internal import ParseadorMensajes

logger = obtener_logger(__name__)

class GenericFilterWorker(WorkerBase):
    def __init__(self):
        super().__init__()
        self.config_filtro = ConfigFiltro()
        self.regla = FabricaReglas.crear(
            self.config_filtro.operador_str,
            self.config_filtro.campo_objetivo,
            self.config_filtro.valor_objetivo_crudo
        )
        self.procesador = ProcesadorLotes(self.regla)
        logger.info(f"[GenericFilter] Iniciado con regla para campo '{self.config_filtro.campo_objetivo}'")

    def coincide(self, transaccion: dict) -> bool:
        return self.regla.coincide(transaccion)

    def procesar_payload(self, queue_name: str, client_id: str, payload: dict | str, mensaje_original: bytes, ack, nack):
        try:
            transaccion = ParseadorMensajes.deserializar(payload)
            
            if transaccion.get(FIN_DE_ARCHIVO):
                logger.info(f"[EOF] Reenviando señal de fin para cliente {client_id}.")
                self._enviar(mensaje_original)
                ack()
                return

            if LOTES in transaccion:
                resultado = self.procesador.procesar_payload(transaccion)
                if resultado:
                    msg_bytes = ParseadorMensajes.serializar(resultado)
                    self._enviar(msg_bytes, payload=resultado)
            else:
                if self.coincide(transaccion):
                    self._enviar(mensaje_original, payload=transaccion)

            ack()

        except Exception as e:
            logger.error(f"Error procesando regla genérica: {e}", exc_info=True)
            nack()

    def al_cerrar(self):
        logger.info("Filtro genérico apagado.")

def main():
    Logger.configurar("filter")
    worker = GenericFilterWorker()
    worker.iniciar()

if __name__ == "__main__":
    main()
