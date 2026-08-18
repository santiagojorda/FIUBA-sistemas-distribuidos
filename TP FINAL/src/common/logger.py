import logging
import os
from pathlib import Path


class Logger:
    _configurado = False

    def __init__(self, nombre):
        self._logger = logging.getLogger(nombre)

    @classmethod
    def configurar(cls, nombre_servicio, archivo_log=None):
        if cls._configurado:
            return

        nivel_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        nivel = getattr(logging, nivel_str, logging.INFO)

        ruta_log = Path(
            archivo_log or os.environ.get("LOG_FILE") or f"logs/{nombre_servicio}.txt"
        )
        ruta_log.parent.mkdir(parents=True, exist_ok=True)

        formato = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

        root = logging.getLogger()
        root.setLevel(nivel)

        for handler in list(root.handlers):
            root.removeHandler(handler)

        handler_archivo = logging.FileHandler(ruta_log, encoding="utf-8")
        handler_archivo.setFormatter(formato)

        handler_consola = logging.StreamHandler()
        handler_consola.setFormatter(formato)

        root.addHandler(handler_archivo)
        root.addHandler(handler_consola)

        logging.getLogger("pika").setLevel(logging.WARNING)
        cls._configurado = True

    def debug(self, mensaje, **kwargs):
        self._logger.debug(mensaje, **kwargs)

    def info(self, mensaje, **kwargs):
        self._logger.info(mensaje, **kwargs)

    def warning(self, mensaje, **kwargs):
        self._logger.warning(mensaje, **kwargs)

    def error(self, mensaje, **kwargs):
        self._logger.error(mensaje, **kwargs)

    def critical(self, mensaje, **kwargs):
        self._logger.critical(mensaje, **kwargs)


def obtener_logger(nombre):
    return Logger(nombre)
