
import os
from common.logger import obtener_logger
import random
import socket
import time
import pika
from functools import wraps
from .middleware import (
    MessageMiddlewareCloseError,
    MessageMiddlewareDisconnectedError,
    MessageMiddlewareMessageError
)

from common import exceptions

_CONNECT_MAX_INTENTOS = int(os.getenv("RABBITMQ_CONNECT_MAX_INTENTOS", "10"))
_CONNECT_DELAY_BASE    = float(os.getenv("RABBITMQ_CONNECT_DELAY_BASE", "1.0"))
_CONNECT_DELAY_CAP     = float(os.getenv("RABBITMQ_CONNECT_DELAY_CAP", "30.0"))

HEARTBEAT_SEGUNDOS = 30
CONEXION_BLOQUEO_SEGUNDOS = 120

# Errores transientes: el servidor todavía no está listo o DNS no resolvió aún.
# Para estos tiene sentido reintentar.
# AMQPConnectionWorkflowFailed existe en pika >= 1.3; getattr lo agrega solo si está disponible.
_ERRORES_TRANSIENTES = tuple(filter(None, [
    socket.gaierror,
    ConnectionRefusedError,
    pika.exceptions.AMQPConnectionError,
    getattr(pika.exceptions, "AMQPConnectionWorkflowFailed", None),
]))

logger = obtener_logger(__name__)

def handle_pika_errors(action_name):
    """Decorador para atrapar excepciones de Pika sin repetir código."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except exceptions.GracefulExitException:
                raise
            except pika.exceptions.AMQPConnectionError as e:
                self._cleanup_resources()
                raise MessageMiddlewareDisconnectedError(f"Conexión perdida al {action_name}") from e
            except pika.exceptions.AMQPChannelError as e:
                self._cleanup_resources()
                raise MessageMiddlewareMessageError(f"Error de canal al {action_name}") from e
            except Exception as e:
                self._cleanup_resources()
                raise MessageMiddlewareMessageError(f"Error interno inesperado al {action_name}") from e
        return wrapper
    return decorator


def handle_pika_send_errors(action_name):
    """Decorador para send(): reconecta y reintenta una vez si se pierde la conexión."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except exceptions.GracefulExitException:
                raise
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"[RabbitMQ] Conexión perdida al {action_name}, reconectando...")
                try:
                    self._reconnect()
                    return func(self, *args, **kwargs)
                except Exception as reconnect_err:
                    self._cleanup_resources()
                    raise MessageMiddlewareDisconnectedError(
                        f"Conexión perdida al {action_name} y reconexión fallida"
                    ) from reconnect_err
            except pika.exceptions.AMQPChannelError as e:
                self._cleanup_resources()
                raise MessageMiddlewareMessageError(f"Error de canal al {action_name}") from e
            except Exception as e:
                self._cleanup_resources()
                raise MessageMiddlewareMessageError(f"Error interno inesperado al {action_name}") from e
        return wrapper
    return decorator


class RabbitMQBase:
    def __init__(self, host):
        self._host = host
        self._port = int(os.getenv("MOM_PORT", "5672"))
        self._user = os.getenv("MOM_USER", "guest")
        self._password = os.getenv("MOM_PASSWORD", "guest")
        self._vhost = os.getenv("MOM_VHOST", "/")
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        ultimo_error = None
        for intento in range(1, _CONNECT_MAX_INTENTOS + 1):
            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=self._host,
                        port=self._port,
                        virtual_host=self._vhost,
                        credentials=pika.PlainCredentials(self._user, self._password),
                        heartbeat=HEARTBEAT_SEGUNDOS,
                        blocked_connection_timeout=CONEXION_BLOQUEO_SEGUNDOS,
                    )
                )
                self.channel = self.connection.channel()
                self.channel.confirm_delivery()
                return
            except _ERRORES_TRANSIENTES as e:
                ultimo_error = e
                delay = min(_CONNECT_DELAY_BASE * (2 ** (intento - 1)), _CONNECT_DELAY_CAP)
                delay += random.uniform(0, delay * 0.2)  # jitter del 20%
                logger.warning(
                    f"[RabbitMQ] Conexión a '{self._host}' fallida (intento {intento}/{_CONNECT_MAX_INTENTOS}): {e}. "
                    f"Reintentando en {delay:.1f}s..."
                )
                time.sleep(delay)
            except Exception as e:
                # Error no transiente (ej: credenciales incorrectas, vhost inexistente).
                # Fallar rápido: reintentar no va a resolver nada.
                raise ConnectionError(f"[RabbitMQ] Error permanente al conectar a '{self._host}': {e}") from e
        raise ConnectionError(
            f"[RabbitMQ] No se pudo conectar a '{self._host}' luego de {_CONNECT_MAX_INTENTOS} intentos: {ultimo_error}"
        )

    def _setup(self):
        """Subclases sobreescriben para re-declarar colas/exchanges tras reconexión."""
        pass

    def _reconnect(self):
        logger.warning(f"[RabbitMQ] Reconectando a {self._host}...")
        self._cleanup_resources()
        self._connect()
        self._setup()
        logger.info("[RabbitMQ] Reconexión exitosa.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _cleanup_resources(self):
        if self.channel and self.channel.is_open:
            try:
                self.channel.close()
            except Exception:
                pass
        if self.connection and self.connection.is_open:
            try:
                self.connection.close()
            except Exception:
                pass
        self.channel = None
        self.connection = None

    def close(self):
        try:
            self._cleanup_resources()
        except Exception as e:
            raise MessageMiddlewareCloseError("Error al cerrar la conexión") from e
