import json
import threading
import time

from common.logger import obtener_logger
from common.crash_hook import CrashHook
from common import crash_points as CP
from common.middleware.middleware_rabbitmq import MessageMiddlewareQueueRabbitMQ


class DetectorLatidos:

    def __init__(self, config, topologia=None):
        self._config = config
        self._logger = obtener_logger("Detector")
        self._hook = CrashHook()
        self._lock = threading.Lock()
        self._ultimo_visto: dict[tuple, float] = {}
        if topologia:
            ahora = time.time()
            for etapa, instancias in topologia.items():
                for instancia in instancias:
                    self._ultimo_visto[(etapa, str(instancia))] = ahora
            self._logger.info(f"Detector inicializado con topología conocida: {topologia}")
        self._evento_parada = threading.Event()
        self._colas_consumidor: list[MessageMiddlewareQueueRabbitMQ] = []
        self._cola_caidas: MessageMiddlewareQueueRabbitMQ | None = None

    def iniciar(self):
        for etapa in self._config.etapas:
            threading.Thread(
                target=self._consumir_etapa,
                args=(etapa,),
                daemon=True,
                name=f"detector-{etapa}",
            ).start()
        threading.Thread(
            target=self._bucle_chequeo,
            daemon=True,
            name="detector-chequeo",
        ).start()
        self._logger.info(
            f"Iniciado. Etapas monitoreadas: {self._config.etapas}. "
            f"Timeout: {self._config.timeout_segundos:.1f}s"
        )

    def detener(self):
        self._evento_parada.set()
        with self._lock:
            colas = list(self._colas_consumidor)
        for cola in colas:
            try:
                cola.stop_consuming()
            except Exception:
                pass

    def _consumir_etapa(self, etapa: str):
        nombre_cola = f"heartbeat.{etapa}"
        try:
            cola = MessageMiddlewareQueueRabbitMQ(self._config.host_mom, nombre_cola)
            with self._lock:
                self._colas_consumidor.append(cola)
            self._logger.info(f"Escuchando {nombre_cola}")
            cola.start_consuming(self._al_recibir_latido)
        except Exception as e:
            if not self._evento_parada.is_set():
                self._logger.error(f"Error consumiendo {nombre_cola}: {e}", exc_info=True)

    def _al_recibir_latido(self, msg: bytes, ack, _):
        try:
            payload = json.loads(msg.decode("utf-8"))
            etapa = payload["etapa"]
            instancia = payload["instancia"]
            ts = payload.get("timestamp", time.time())
            with self._lock:
                self._ultimo_visto[(etapa, instancia)] = ts
            ack()
        except Exception as e:
            self._logger.warning(f"Heartbeat malformado: {e}")
            ack()

    def _bucle_chequeo(self):
        while not self._evento_parada.wait(self._config.intervalo_chequeo_segundos):
            ahora = time.time()
            with self._lock:
                snapshot = dict(self._ultimo_visto)

            caidas = [
                (etapa, instancia)
                for (etapa, instancia), ultimo_ts in snapshot.items()
                if ahora - ultimo_ts > self._config.timeout_segundos
            ]

            for etapa, instancia in caidas:
                transcurrido = ahora - snapshot[(etapa, instancia)]
                self._logger.warning(
                    f"Caída detectada: {etapa}/{instancia} "
                    f"(último heartbeat hace {transcurrido:.1f}s)"
                )
                self._publicar_caida(etapa, instancia)

    def registrar_nodo(self, etapa: str, instancia: str):
        with self._lock:
            if (etapa, instancia) not in self._ultimo_visto:
                self._ultimo_visto[(etapa, instancia)] = time.time()
                self._logger.info(f"Nodo registrado dinámicamente: {etapa}/{instancia}")

    def _publicar_caida(self, etapa: str, instancia: str):
        self._hook.verificar(CP.WD_PRE_PUBLISH_CAIDA, f"pre-publish {etapa}/{instancia}")
        try:
            if self._cola_caidas is None:
                self._cola_caidas = MessageMiddlewareQueueRabbitMQ(
                    self._config.host_mom,
                    self._config.cola_caidas,
                )
            self._cola_caidas.send(json.dumps({"etapa": etapa, "instancia": instancia}).encode("utf-8"))
            with self._lock:
                self._ultimo_visto.pop((etapa, instancia), None)
            self._logger.info(f"Evento de caída publicado: {etapa}/{instancia}")
        except Exception as e:
            self._logger.error(f"Error publicando caída de {etapa}/{instancia}: {e}", exc_info=True)
