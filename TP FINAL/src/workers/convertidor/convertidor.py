from base.worker_base import WorkerBase
from common.logger import Logger, obtener_logger
from common.message_protocol.internal import ParseadorMensajes
from common.constantes_protocolo import (
    ID_CLIENTE,
    LOTES,
    ID_SOLICITUD,
)
from config_convertidor import ConfigConvertidor
from cliente_cotizaciones import ClienteCotizaciones
from conversor_moneda import ConversorMoneda
from procesador_lotes import ProcesadorLotesConvertidor

logger = obtener_logger(__name__)

class WorkerConvertidorMonedas(WorkerBase):
    def __init__(self):
        super().__init__()
        self.config_convertidor = ConfigConvertidor()
        self.cliente = ClienteCotizaciones(self.config_convertidor.fecha_inicio, self.config_convertidor.fecha_fin)
        self.cotizaciones = self.cliente.obtener_cotizaciones()
        self.conversor = ConversorMoneda(self.cotizaciones)
        self.procesador = ProcesadorLotesConvertidor(self.conversor)

    def procesar_payload(self, queue_name: str, client_id: str, payload: dict | str, mensaje_original: bytes, ack, nack):
        try:
            transaccion = ParseadorMensajes.deserializar(payload)
            
            if LOTES in transaccion:
                lotes_filtrados = self.procesador.procesar_payload(transaccion, client_id)
                if lotes_filtrados:
                    payload_salida = {
                        ID_CLIENTE: client_id,
                        LOTES: lotes_filtrados
                    }
                    if ID_SOLICITUD in transaccion:
                        payload_salida[ID_SOLICITUD] = transaccion[ID_SOLICITUD]
                    msg_bytes = ParseadorMensajes.serializar(payload_salida)
                    self._enviar(msg_bytes, payload=payload_salida)
            else:
                if self.procesador.coincide_limite(transaccion):
                    self._enviar(mensaje_original)

            ack()

        except (ValueError, KeyError) as e:
            logger.warning(f"Error parseando transacción: {e}. Descartando.")
            ack()
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)
            nack()

    def al_cerrar(self):
        logger.info("Convertidor apagado.")

def main():
    Logger.configurar("converter")
    WorkerConvertidorMonedas().iniciar()

if __name__ == "__main__":
    main()
