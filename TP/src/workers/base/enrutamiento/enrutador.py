import threading
from common.logger import obtener_logger
from common import middleware
from common.message_protocol.internal import ParseadorMensajes
from common.constantes_protocolo import (
    ID_CLIENTE,
    FIN_DE_ARCHIVO,
    DESCONEXION_CLIENTE,
)
from base.constantes import (
    CONF_TIPO,
    CONF_CONDICIONAL,
    CONF_TOTAL_WORKERS,
)
from .colas_salida import ColaSalidaDirecta, ColaSalidaSharded, ColaSalidaCondicional

logger = obtener_logger(__name__)


class EnrutadorMensajes:
    def __init__(self, config):
        self._config = config
        self.colas_entrada = {}
        self._colas_salida = []
        self._lock_envio = threading.Lock()
        self._configurar_colas()

    def _configurar_colas(self):
        for cola in self._config.colas_entrada:
            nombre = cola.replace("{id}", str(self._config.id_nodo))
            self.colas_entrada[nombre] = middleware.MessageMiddlewareQueueRabbitMQ(
                self._config.host_mom, nombre
            )

        for item in self._config.colas_salida:
            if isinstance(item, str):
                self._colas_salida.append(
                    ColaSalidaDirecta(self._config.host_mom, item)
                )
            elif isinstance(item, dict):
                if item.get(CONF_TIPO) == CONF_CONDICIONAL:
                    self._colas_salida.append(
                        ColaSalidaCondicional(self._config.host_mom, item)
                    )
                else:
                    total = int(item.get(CONF_TOTAL_WORKERS) or 0)
                    if total > 0:
                        self._colas_salida.append(
                            ColaSalidaSharded(self._config.host_mom, item)
                        )

    def enviar(self, mensaje: bytes, payload: dict | None = None,
               id_solicitud_origen: str | None = None):
        with self._lock_envio:
            self._enviar_con_lock(mensaje, payload, id_solicitud_origen)

    def _enviar_con_lock(self, mensaje: bytes, payload: dict | None,
                         id_solicitud_origen: str | None):
        try:
            if mensaje is None:
                return

            payload = self._asegurar_payload(mensaje, payload)
            es_eof = payload.get(FIN_DE_ARCHIVO, False) or payload.get(DESCONEXION_CLIENTE, False)
            client_id = payload.get(ID_CLIENTE)

            for cola in self._colas_salida:
                cola.enviar(mensaje, payload, es_eof, client_id, id_solicitud_origen)

        except Exception as e:
            logger.error(f"Error crítico en el ruteo: {e}", exc_info=True)

    def _asegurar_payload(self, mensaje: bytes, payload: dict | None) -> dict:
        if payload is not None:
            return payload
        try:
            return ParseadorMensajes.deserializar(mensaje)
        except Exception:
            return {}

    def detener_consumo(self):
        for cola in self.colas_entrada.values():
            cola.stop_consuming()

    def cerrar(self):
        for cola in self.colas_entrada.values():
            cola.close()
        for cola in self._colas_salida:
            cola.cerrar()
