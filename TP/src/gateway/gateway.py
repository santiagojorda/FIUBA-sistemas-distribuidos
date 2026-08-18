import json
import socket
import threading
import signal
import sys
import time
from config import GatewayConfig
from state import GatewayState
from backend import BackendListener
from client_handler import ClientHandler
from common.logger import Logger, obtener_logger
from common import middleware

logger = obtener_logger(__name__)


def _emitir_latidos(config: GatewayConfig, evento_cierre: threading.Event):
    """Publica heartbeats en heartbeat.gateway para que el watchdog detecte caídas."""
    intervalo = float(config.heartbeat_interval_seconds)
    if intervalo <= 0:
        return

    cola = None
    while not evento_cierre.is_set():
        try:
            if cola is None:
                cola = middleware.MessageMiddlewareQueueRabbitMQ(config.mom_host, "heartbeat.gateway")
            payload = json.dumps({"etapa": "gateway", "instancia": "01", "timestamp": time.time()})
            cola.send(payload.encode("utf-8"))
        except Exception as e:
            logger.warning(f"[Gateway] Error enviando heartbeat: {e}")
            if cola is not None:
                try:
                    cola.close()
                except Exception:
                    pass
                cola = None
        evento_cierre.wait(intervalo)

    if cola is not None:
        try:
            cola.close()
        except Exception:
            pass


def main():
    Logger.configurar("gateway")

    config = GatewayConfig()
    state = GatewayState()
    backend_listener = BackendListener(config, state)
    client_handler = ClientHandler(config, state)

    for cola_nombre in config.input_queues:
        if cola_nombre:
            t = threading.Thread(
                target=backend_listener.escuchar,
                args=(cola_nombre,),
                daemon=True
            )
            t.start()

    evento_cierre = threading.Event()
    threading.Thread(
        target=_emitir_latidos,
        args=(config, evento_cierre),
        daemon=True,
        name="gateway-heartbeat"
    ).start()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.server_host, config.server_port))
    server_socket.listen()

    logger.info(f"Gateway listo en {config.server_host}:{config.server_port}")

    def cerrar_graceful(sig, frame):
        logger.info("Apagando Gateway...")
        evento_cierre.set()
        state.detener_servidor()
        server_socket.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, cerrar_graceful)
    signal.signal(signal.SIGTERM, cerrar_graceful)

    try:
        while state.servidor_corriendo:
            client_sock, _ = server_socket.accept()
            hilo_cliente = threading.Thread(
                target=client_handler.atender,
                args=(client_sock,),
                daemon=True
            )
            hilo_cliente.start()
    except Exception:
        pass
    finally:
        evento_cierre.set()
        server_socket.close()


if __name__ == "__main__":
    main()
