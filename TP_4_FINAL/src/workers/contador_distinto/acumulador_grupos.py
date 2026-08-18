import threading


class AcumuladorGrupos:
    """
    Mantiene en memoria el estado de agrupación por cliente de forma thread-safe.

    Estructura interna:
      _grupos:        dict[client_id -> dict[clave_grupo -> set[clave_valor]]]
      _vistos:        dict[client_id -> set[request_id]]  (deduplicación)
      _pending_acks:  dict[client_id -> list[callable]]   (acks a liberar tras persistir)
    """

    def __init__(self):
        self._grupos: dict[str, dict[tuple, set]] = {}
        self._vistos: dict[str, set] = {}
        self._pending_acks: dict[str, list] = {}
        self._lock = threading.Lock()

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    # --- escritura ---

    def agregar(self, client_id: str, clave_grupo: tuple, clave_valor: tuple):
        """Acumula un valor distinto dentro del grupo correspondiente."""
        self._grupos.setdefault(client_id, {}).setdefault(clave_grupo, set()).add(clave_valor)

    def marcar_visto(self, client_id: str, request_id: str):
        self._vistos.setdefault(client_id, set()).add(request_id)

    def registrar_ack(self, client_id: str, ack):
        self._pending_acks.setdefault(client_id, []).append(ack)

    def restaurar(self, client_id: str, grupos: dict, vistos: set):
        """Carga estado recuperado desde disco (llamar dentro del lock)."""
        self._grupos[client_id] = grupos
        self._vistos[client_id] = vistos

    # --- lectura ---

    def ya_visto(self, client_id: str, request_id: str) -> bool:
        return request_id in self._vistos.get(client_id, set())

    def snapshot_grupos(self, client_id: str) -> dict:
        """Retorna los grupos del cliente sin modificar el estado."""
        return self._grupos.get(client_id, {})

    def snapshot_vistos(self, client_id: str) -> set:
        """Retorna los vistos del cliente sin modificar el estado."""
        return self._vistos.get(client_id, set())

    def total_acks_pendientes(self) -> int:
        return sum(len(v) for v in self._pending_acks.values())

    def clientes_con_acks(self) -> list[str]:
        return list(self._pending_acks.keys())

    # --- extracción (destructiva) ---

    def extraer_acks(self, client_id: str) -> list:
        """Extrae y retorna los acks pendientes del cliente."""
        return self._pending_acks.pop(client_id, [])

    def extraer_grupos(self, client_id: str) -> dict:
        """Extrae y retorna los grupos del cliente, limpiando su estado completo."""
        grupos = self._grupos.pop(client_id, {})
        self._vistos.pop(client_id, None)
        self._pending_acks.pop(client_id, None)
        return grupos
