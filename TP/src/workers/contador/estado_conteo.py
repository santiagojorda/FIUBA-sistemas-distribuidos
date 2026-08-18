import threading
from common.constantes_protocolo import CABECERA, CANTIDAD, LOTES, PAYLOAD
from persistencia_conteo import PersistenciaConteo


def calcular_cantidad(payload: dict) -> int:
    if LOTES in payload:
        return sum(
            int(lote[CABECERA].get(CANTIDAD, len(lote[PAYLOAD])))
            for lote in payload[LOTES]
        )
    return 1



class EstadoConteo:

    def __init__(self, id_nodo: int):
        self._persistencia = PersistenciaConteo(id_nodo)
        self._conteos, self._ids_procesados = self._persistencia.recuperar_estado()
        self._lock = threading.Lock()

    def incrementar(self, client_id: str, cantidad: int, request_id: str | None) -> bool:
        """
        Incrementa el conteo para un cliente si el request_id no fue procesado aún.
        Retorna True si el mensaje ya había sido procesado (duplicado), False en caso contrario.
        """
        with self._lock:
            if request_id:
                if client_id not in self._ids_procesados:
                    self._ids_procesados[client_id] = set()
                if request_id in self._ids_procesados[client_id]:
                    return True
                self._ids_procesados[client_id].add(request_id)

            self._conteos[client_id] = self._conteos.get(client_id, 0) + cantidad
            self._persistencia.guardar(client_id, self._conteos[client_id], self._ids_procesados.get(client_id, set()))
            return False

    def obtener_y_limpiar(self, client_id: str) -> int:
        with self._lock:
            self._ids_procesados.pop(client_id, None)
            return self._conteos.pop(client_id, 0)

    def descartar(self, client_id: str):
        with self._lock:
            self._ids_procesados.pop(client_id, None)
            self._conteos.pop(client_id, None)
        self._persistencia.borrar(client_id)

    def marcar_completado(self, client_id: str):
        self._persistencia.marcar_completado(client_id)

    def ya_completado(self, client_id: str) -> bool:
        return self._persistencia.esta_completado(client_id)

