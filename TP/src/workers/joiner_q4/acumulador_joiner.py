import threading


class AcumuladorJoiner:
    """
    Mantiene en memoria el estado del join por cliente de forma thread-safe.

    Estructura interna:
      _scatter:      dict[client_id -> dict[b_key -> list[a_info_tuple]]]
                     Usa lista porque append no es idempotente — _vistos
                     protege contra reenvíos duplicados.
      _txns:         dict[client_id -> dict[b_key -> set[c_info_tuple]]]
                     Usa set porque la misma transacción puede llegar varias
                     veces sin importar (idempotente).
      _vistos:       dict[client_id -> set[request_id]]
      _pending_acks: dict[client_id -> list[callable]]
    """

    def __init__(self):
        self._scatter: dict[str, dict[str, list]] = {}
        self._txns: dict[str, dict[str, set]] = {}
        self._vistos: dict[str, set] = {}
        self._pending_acks: dict[str, list] = {}
        self._lock = threading.Lock()

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    # --- escritura ---

    def agregar_arista(self, client_id: str, b_key: str, a_info: tuple):
        """Acumula la arista A→B en la lista del índice scatter."""
        self._scatter.setdefault(client_id, {}).setdefault(b_key, []).append(a_info)

    def agregar_transaccion(self, client_id: str, b_key: str, c_info: tuple):
        """Acumula la transacción B→C en el set del índice de txns."""
        self._txns.setdefault(client_id, {}).setdefault(b_key, set()).add(c_info)

    def marcar_visto(self, client_id: str, request_id: str):
        self._vistos.setdefault(client_id, set()).add(request_id)

    def registrar_ack(self, client_id: str, ack):
        self._pending_acks.setdefault(client_id, []).append(ack)

    def restaurar(self, client_id: str, scatter: dict, txns: dict, vistos: set):
        """Carga estado recuperado desde disco (llamar dentro del lock)."""
        self._scatter[client_id] = scatter
        self._txns[client_id] = txns
        self._vistos[client_id] = vistos

    # --- lectura ---

    def ya_visto(self, client_id: str, request_id: str) -> bool:
        return request_id in self._vistos.get(client_id, set())

    def snapshot_scatter(self, client_id: str) -> dict:
        return self._scatter.get(client_id, {})

    def snapshot_txns(self, client_id: str) -> dict:
        return self._txns.get(client_id, {})

    def snapshot_vistos(self, client_id: str) -> set:
        return self._vistos.get(client_id, set())

    def total_acks_pendientes(self) -> int:
        return sum(len(v) for v in self._pending_acks.values())

    def clientes_con_acks(self) -> list[str]:
        return list(self._pending_acks.keys())

    # --- extracción (destructiva) ---

    def extraer_acks(self, client_id: str) -> list:
        """Extrae y retorna los acks pendientes del cliente."""
        return self._pending_acks.pop(client_id, [])

    def extraer_cliente(self, client_id: str) -> tuple[dict, dict]:
        """Extrae y retorna (scatter, txns), limpiando todo el estado del cliente."""
        scatter = self._scatter.pop(client_id, {})
        txns = self._txns.pop(client_id, {})
        self._vistos.pop(client_id, None)
        self._pending_acks.pop(client_id, None)
        return scatter, txns
