import threading


class ContadorVuelos:
    def __init__(self):
        self._conteos = {}
        self._lock = threading.Lock()
        self._condicion = threading.Condition(self._lock)

    def registrar(self, client_id):
        with self._lock:
            self._conteos[client_id] = self._conteos.get(client_id, 0) + 1

    def descontar(self, client_id):
        with self._lock:
            if client_id in self._conteos:
                self._conteos[client_id] -= 1
                if self._conteos[client_id] <= 0:
                    del self._conteos[client_id]
                self._condicion.notify_all()

    def esperar_cero(self, client_id):
        with self._lock:
            while self._conteos.get(client_id, 0) > 0:
                self._condicion.wait()

    def limpiar(self, client_id):
        with self._lock:
            self._conteos.pop(client_id, None)
