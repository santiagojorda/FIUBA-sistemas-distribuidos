import json
import os

import docker
import docker.errors
from common.logger import obtener_logger
from common.middleware.middleware_rabbitmq import MessageMiddlewareQueueRabbitMQ


class Actuador:

    def __init__(self):
        self._logger = obtener_logger("Actuador")
        self._host_mom = os.getenv("MOM_HOST", "localhost")
        self._nombre_cola_caidas = os.getenv("CAIDAS_QUEUE", "caidas")
        self._cola: MessageMiddlewareQueueRabbitMQ | None = None
        self._docker = docker.from_env()

    def iniciar(self):
        self._cola = MessageMiddlewareQueueRabbitMQ(self._host_mom, self._nombre_cola_caidas)
        self._logger.info(f"Escuchando cola '{self._nombre_cola_caidas}'.")
        self._cola.start_consuming(self._al_recibir_caida)

    def detener(self):
        if self._cola is not None:
            try:
                self._cola.stop_consuming()
            except Exception:
                pass

    def _al_recibir_caida(self, msg: bytes, ack, nack):
        try:
            evento = json.loads(msg.decode("utf-8"))
            etapa = evento["etapa"]
            instancia = evento["instancia"]
        except (json.JSONDecodeError, KeyError) as e:
            self._logger.warning(f"Mensaje de caída malformado: {e}")
            ack()
            return

        nombre_container = f"{etapa}_{instancia}"
        try:
            self._reiniciar(nombre_container)
            ack()
        except docker.errors.NotFound:
            self._logger.warning(f"Container '{nombre_container}' no encontrado — ignorando.")
            ack()
        except Exception as e:
            self._logger.error(f"Error reiniciando '{nombre_container}': {e}", exc_info=True)
            nack()

    def _reiniciar(self, nombre_container: str):
        container = self._docker.containers.get(nombre_container)
        container.reload()
        estado = container.status
        if estado != "running":
            self._logger.info(f"Container '{nombre_container}' no está corriendo (estado={estado}). Iniciando con start()...")
            container.start()
        else:
            self._logger.info(f"Container '{nombre_container}' está corriendo pero colgado (estado={estado}). Reiniciando con restart()...")
            container.restart()
        self._logger.info(f"Container '{nombre_container}' levantado exitosamente.")
