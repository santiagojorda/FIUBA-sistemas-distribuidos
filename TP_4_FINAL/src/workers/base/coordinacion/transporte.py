import threading
from common.logger import obtener_logger
from common import middleware
from common.message_protocol.internal import ParseadorMensajes
from common.constantes_protocolo import ID_CLIENTE
from base.constantes import TIPO_MENSAJE


logger = obtener_logger(__name__)


class TransporteControl:
    def __init__(self, config):
        self._id_nodo = config.id_nodo
        self._envio_lock = threading.Lock()
        self.exchange = middleware.FanoutExchangeRabbitMQ(
            config.host_mom, f"control_{config.prefijo_nodo}_exchange"
        )
        self.cola = middleware.FanoutQueueRabbitMQ(
            config.host_mom,
            f"control_{config.prefijo_nodo}_queue_{config.id_nodo}",
            self.exchange.exchange_name,
        )

    def enviar(self, msg_dict):
        try:
            logger.info(
                f"Enviando control {msg_dict.get(TIPO_MENSAJE)} "
                f"para client_id={msg_dict.get(ID_CLIENTE)} "
                f"desde worker {self._id_nodo}."
            )
            with self._envio_lock:
                self.exchange.send(ParseadorMensajes.serializar(msg_dict))
        except Exception as e:
            logger.error(f"Error enviando control: {e}")

    def iniciar_consumo(self, callback):
        self.cola.start_consuming(callback)

    def detener_consumo(self):
        self.cola.stop_consuming()

    def cerrar(self):
        self.cola.close()
        self.exchange.close()
