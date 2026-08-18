import json
import time
from common.logger import obtener_logger
import threading
from common import middleware

logger = obtener_logger(__name__)


class Latido:
    def __init__(self, host_mom, prefijo_nodo, id_nodo, intervalo, evento_cierre, nombre_clase):
        self._host_mom = host_mom
        self._nombre_cola = f"heartbeat.{prefijo_nodo}"
        self._etapa = prefijo_nodo
        self._id_instancia = f"{id_nodo:02d}"
        self._intervalo = intervalo
        self._evento_cierre = evento_cierre
        self._nombre_clase = nombre_clase
        self._hilo = None

    def iniciar(self):
        if self._intervalo <= 0:
            logger.info(
                f"[{self._nombre_clase}] Heartbeat deshabilitado "
                f"(intervalo={self._intervalo})."
            )
            return

        self._evento_cierre.clear()
        self._hilo = threading.Thread(
            target=self._bucle,
            name=f"{self._nombre_clase}-heartbeat",
            daemon=True,
        )
        self._hilo.start()

    def _bucle(self):
        cola = None
        try:
            while not self._evento_cierre.is_set():
                try:
                    if cola is None:
                        cola = middleware.MessageMiddlewareQueueRabbitMQ(
                            self._host_mom, self._nombre_cola,
                        )
                    payload = {
                        "etapa": self._etapa,
                        "instancia": self._id_instancia,
                        "timestamp": time.time(),
                    }
                    cola.send(json.dumps(payload).encode("utf-8"))
                except Exception as e:
                    if cola is not None:
                        try:
                            cola.close()
                        except Exception:
                            pass
                        cola = None
                    if not self._evento_cierre.is_set():
                        logger.warning(
                            f"[{self._nombre_clase}] Error enviando heartbeat: {e}",
                            exc_info=True,
                        )
                if self._evento_cierre.wait(self._intervalo):
                    break
        finally:
            if cola is not None:
                try:
                    cola.close()
                except Exception as e:
                    logger.warning(
                        f"[{self._nombre_clase}] Error cerrando heartbeat: {e}"
                    )
