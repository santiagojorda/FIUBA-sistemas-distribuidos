
import pika
from functools import wraps
from .middleware import (
    MessageMiddlewareCloseError, 
    MessageMiddlewareDisconnectedError, 
    MessageMiddlewareMessageError
)

from common import exceptions

def handle_pika_errors(action_name):
    """Decorador para atrapar excepciones de Pika sin repetir código."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except exceptions.GracefulExit:
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


class RabbitMQBase:
    def __init__(self, host):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=host))
        self.channel = self.connection.channel()

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
