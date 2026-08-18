import json
import signal
import threading

from common.logger import Logger, obtener_logger
from common.middleware.middleware_rabbitmq import MessageMiddlewareQueueRabbitMQ
from configuracion import ConfiguracionWatchdog
from detector import DetectorLatidos
from eleccion_anillo import EleccionAnillo


def _publicar_caidas_watchdogs(logger, config: ConfiguracionWatchdog, ids_caidos: list[int]):
    if not ids_caidos:
        return
    try:
        cola = MessageMiddlewareQueueRabbitMQ(config.host_mom, config.cola_caidas)
        for id_wd in ids_caidos:
            evento = {"etapa": "watchdog", "instancia": str(id_wd)}
            cola.send(json.dumps(evento).encode())
            logger.info(f"Caída publicada para reinicio: watchdog_{id_wd}")
    except Exception as e:
        logger.error(f"Error publicando caídas de watchdogs: {e}", exc_info=True)


def main():
    Logger.configurar("watchdog")
    config = ConfiguracionWatchdog()
    logger = obtener_logger(f"Watchdog-{config.id_watchdog}")

    if not config.etapas:
        logger.warning("WATCHDOG_STAGES está vacío — no hay nada que monitorear.")

    detector_actual: DetectorLatidos | None = None
    detector_activo = False
    lock_detector = threading.Lock()

    def al_ser_lider(ids_watchdogs_caidos: list[int]):
        nonlocal detector_activo, detector_actual
        with lock_detector:
            if not detector_activo:
                detector_activo = True
                detector_actual = DetectorLatidos(config, topologia=eleccion.obtener_topologia_serializable())
                detector_actual.iniciar()
                logger.info("Soy el líder. Detector de caídas activo.")
        _publicar_caidas_watchdogs(logger, config, ids_watchdogs_caidos)

    def al_perder_liderazgo():
        nonlocal detector_activo, detector_actual
        with lock_detector:
            if detector_activo:
                detector_activo = False
                if detector_actual is not None:
                    detector_actual.detener()
                    detector_actual = None
                logger.info("Perdí el liderazgo. Detector detenido.")

    def al_caer_standby(id_nodo: int):
        logger.warning(f"Standby watchdog_{id_nodo} caído — publicando para reinicio.")
        _publicar_caidas_watchdogs(logger, config, [id_nodo])

    def al_registrar_nodo(etapa: str, instancia: str):
        with lock_detector:
            if detector_actual is not None:
                detector_actual.registrar_nodo(etapa, instancia)

    eleccion = EleccionAnillo(config, al_ser_lider, al_perder_liderazgo, al_caer_standby, al_registrar_nodo)
    evento_parada = threading.Event()

    def manejar_senal(signum, frame):
        logger.info("Señal recibida. Cerrando...")
        eleccion.detener()
        with lock_detector:
            if detector_actual is not None:
                detector_actual.detener()
        evento_parada.set()

    signal.signal(signal.SIGTERM, manejar_senal)
    signal.signal(signal.SIGINT, manejar_senal)

    logger.info(f"Iniciando. Anillo de {config.cantidad_watchdogs} nodos.")
    eleccion.iniciar()

    evento_parada.wait()
    logger.info("Apagado completo.")


if __name__ == "__main__":
    main()
