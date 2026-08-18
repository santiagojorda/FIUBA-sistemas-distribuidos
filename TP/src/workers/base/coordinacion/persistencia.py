import threading
from common.logger import obtener_logger
from common.persistencia import PersistidorEstado
from common.message_protocol.internal import ParseadorMensajes
from .estado_cliente import EstadoClienteCoordinacion

logger = obtener_logger(__name__)


class PersistenciaCoordinacion:
    def __init__(self, nombre_nodo):
        self._persistidor = PersistidorEstado(nombre_nodo)
        self._lock = threading.Lock()

    @property
    def directorio(self):
        return self._persistidor.directory

    def guardar(self, clientes):
        with self._lock:
            coordinaciones = {}
            eofs_locales = {}
            flush_completados = {}
            clientes_finalizados = []

            for client_id, ec in clientes.items():
                if ec.barrera_activa:
                    mensaje_payload = None
                    if ec.mensaje_original:
                        try:
                            mensaje_payload = ParseadorMensajes.deserializar(
                                ec.mensaje_original
                            )
                        except Exception:
                            pass
                    coordinaciones[client_id] = {
                        "workers_confirmados": list(ec.workers_confirmados),
                        "mensaje_payload": mensaje_payload,
                        "worker_conteos": ec.worker_conteos,
                    }

                if ec.eofs_locales:
                    eofs_locales[client_id] = list(ec.eofs_locales)

                if ec.originador_flush is not None:
                    flush_completados[client_id] = ec.originador_flush

                if ec.finalizado:
                    clientes_finalizados.append(client_id)

            self._persistidor.guardar({
                "coordinaciones_eof": coordinaciones,
                "eofs_locales_recibidos": eofs_locales,
                "flush_completados": flush_completados,
                "clientes_finalizados": clientes_finalizados,
            })

    def cargar(self, id_nodo, total_workers):
        estado = self._persistidor.cargar()
        clientes = {}
        barreras_pendientes = []
        worker_finished_pendientes = []

        for client_id, colas in estado.get("eofs_locales_recibidos", {}).items():
            clientes.setdefault(client_id, EstadoClienteCoordinacion()).eofs_locales = set(colas)

        for client_id, datos in estado.get("coordinaciones_eof", {}).items():
            mensaje_original = None
            if datos.get("mensaje_payload"):
                mensaje_original = ParseadorMensajes.serializar(datos["mensaje_payload"])

            ec = clientes.setdefault(client_id, EstadoClienteCoordinacion())
            ec.workers_confirmados = set(datos.get("workers_confirmados", []))
            ec.worker_conteos = datos.get("worker_conteos", {})
            ec.mensaje_original = mensaje_original
            ec.barrera_activa = True
            ec.originador = id_nodo
            ec.eof_local_completo = True
            logger.info(
                f"Recuperando coordinación para {client_id}: "
                f"{len(ec.workers_confirmados)}/{total_workers} confirmados."
            )

            if len(ec.workers_confirmados) >= total_workers:
                logger.info(
                    f"La barrera para {client_id} ya estaba completa. "
                    f"Encolando para reenviar."
                )
                barreras_pendientes.append((client_id, mensaje_original))

        for client_id in estado.get("clientes_finalizados", []):
            clientes.setdefault(client_id, EstadoClienteCoordinacion()).finalizado = True
            logger.info(f"Recuperando cliente finalizado: {client_id}.")

        for client_id, originador in estado.get("flush_completados", {}).items():
            ec = clientes.setdefault(client_id, EstadoClienteCoordinacion())
            ec.flusheado = True
            ec.eof_local_completo = True
            ec.originador = originador
            ec.originador_flush = originador
            worker_finished_pendientes.append((client_id, originador))
            logger.info(
                f"Recuperando flush pendiente para {client_id}: "
                f"reenviando al originador {originador}."
            )

        return clientes, barreras_pendientes, worker_finished_pendientes
