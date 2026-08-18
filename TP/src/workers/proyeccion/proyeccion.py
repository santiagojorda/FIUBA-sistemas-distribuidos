import json

from base.worker_base import WorkerBase
from common.logger import Logger, obtener_logger
from common.constantes_protocolo import FIN_DE_ARCHIVO, LOTES, ID_CLIENTE, ID_SOLICITUD
from config_proyeccion import ConfigProyeccion
from procesador_proyeccion import ProcesadorLotes

logger = obtener_logger(__name__)


class WorkerProyeccion(WorkerBase):
    """
    Worker genérico de proyección de campos.

    Filtra cada registro conservando solo los campos listados en CAMPOS.
    Opcionalmente convierte a entero los campos en INT_FIELDS.

    Variables de entorno:
      CAMPOS      campos a conservar, separados por coma
      INT_FIELDS  campos a convertir a entero, separados por coma (opcional)
    """

    def __init__(self):
        super().__init__()
        self.config_proyeccion = ConfigProyeccion()
        self.procesador = ProcesadorLotes(
            self.config_proyeccion.campos,
            self.config_proyeccion.campos_enteros,
        )
        logger.info(
            f"[WorkerProyeccion] campos={self.config_proyeccion.campos} "
            f"campos_enteros={self.config_proyeccion.campos_enteros}"
        )

    def procesar_payload(self, queue_name: str, client_id: str, payload: dict,
                         mensaje_original: bytes, ack, nack):
        try:
            if payload.get(FIN_DE_ARCHIVO):
                self._enviar(mensaje_original)
                ack()
                return

            if LOTES in payload:
                resultado = self.procesador.procesar_payload(payload, client_id)
                if resultado:
                    self._enviar(json.dumps(resultado).encode("utf-8"), payload=resultado)
            else:
                proyectado = self.procesador.procesar_individual(payload, client_id)
                self._enviar(json.dumps(proyectado).encode("utf-8"), payload=proyectado)

            ack()
        except Exception as e:
            logger.error(f"Error proyectando payload: {e}", exc_info=True)
            nack()

    def al_completar_cliente(self, client_id: str):
        # Cada worker envía su propio EOF por su propia conexión TCP, garantizando
        # que sus datos lleguen a RabbitMQ antes que este EOF (ordering por conexión).
        eof_sintetico = json.dumps({
            ID_CLIENTE: client_id,
            FIN_DE_ARCHIVO: True,
            ID_SOLICITUD: f"_peof_{self.configuracion.id_nodo}_{client_id[:8]}",
        }).encode("utf-8")
        self._enviar(eof_sintetico)

    def al_cerrar(self):
        logger.info("[WorkerProyeccion] Apagado.")


def main():
    Logger.configurar("proyeccion")
    WorkerProyeccion().iniciar()


if __name__ == "__main__":
    main()
