import json

class ParseadorMensajes:
    @staticmethod
    def deserializar(datos: str | bytes | dict) -> dict:
        if isinstance(datos, dict):
            return datos
        if isinstance(datos, bytes):
            datos = datos.decode("utf-8")
        return json.loads(datos)

    @staticmethod
    def serializar(payload: dict) -> bytes:
        return json.dumps(payload).encode("utf-8")

def es_eof(payload: dict) -> bool:
    return isinstance(payload, dict) and set(payload.keys()) == {"client_id"}

def es_dato(payload: dict) -> bool:
    return isinstance(payload, dict) and not es_eof(payload)

def crear_eof(client_id: int) -> bytes:
    return ParseadorMensajes.serializar({"client_id": int(client_id)})

def crear_dato(record: dict) -> bytes:
    return ParseadorMensajes.serializar(record)

def obtener_id_cliente(payload: dict) -> int:
    return int(payload["client_id"])

def crear_desconexion_cliente(client_id: str) -> bytes:
    return ParseadorMensajes.serializar({"client_id": client_id, "CLIENT_DISCONNECT": True})

def es_desconexion_cliente(payload: dict) -> bool:
    return isinstance(payload, dict) and payload.get("CLIENT_DISCONNECT") is True
