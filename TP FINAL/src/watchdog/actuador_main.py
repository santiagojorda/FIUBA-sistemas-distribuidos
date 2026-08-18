import signal

from common.logger import Logger, obtener_logger
from actuador import Actuador


def main():
    Logger.configurar("actuador")
    logger = obtener_logger("Actuador")

    actuador = Actuador()

    def manejar_senal(signum, frame):
        logger.info("Señal recibida. Cerrando...")
        actuador.detener()

    signal.signal(signal.SIGTERM, manejar_senal)
    signal.signal(signal.SIGINT, manejar_senal)

    logger.info("Iniciando.")
    actuador.iniciar()
    logger.info("Apagado completo.")


if __name__ == "__main__":
    main()
