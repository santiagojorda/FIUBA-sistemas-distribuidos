from asyncio import IncompleteReadError
import json
from common.logger import obtener_logger
from common.constantes_protocolo import CABECERA, ESQUEMA, PAYLOAD, ID_CLIENTE, CANTIDAD

from . import external_serializer


logger = obtener_logger(__name__)


class TipoMensaje:
    ACK = 3
    FIN_DE_REGISTROS = 4
    REPORTE = 5
    LOTE_TRANSACCIONES = 6
    LOTE_BANCOS = 7
    CONFIG_QUERIES = 8
    HELLO = 9  # El cliente lo envía primero con su client_id para soportar reconexión
    ACK_RESULTADO = 10  # El cliente confirma recepción de un batch de resultados (contiene batch_id)


def _recibir_tamanio(socket, size):
    """
    Recibe exactamente 'size' bytes a través del socket.
    Si no se leen bytes del socket se lanza IncompleteReadError.
    """
    buf = bytearray(size)
    pos = 0
    while pos < size:
        n = socket.recv_into(memoryview(buf)[pos:])
        if n == 0:
            raise IncompleteReadError(bytes(buf[:pos]), size)
        pos += n
    return bytes(buf)


def _recibir_vacio(socket):
    return None


def _recibir_reporte(socket):
    tamanio_reporte = external_serializer.deserializar_uint32(
        _recibir_tamanio(socket, external_serializer.TAMANIO_UINT32)
    )

    # Capturamos los bytes brutos ANTES de decodificarlos
    bytes_crudos = _recibir_tamanio(socket, tamanio_reporte)

    try:
        reporte = bytes_crudos.decode("utf-8")
    except UnicodeDecodeError:
        logger.error("DEBUG CRÍTICO: Recibidos %s bytes que no son UTF-8: %s", tamanio_reporte, bytes_crudos.hex())
        raise

    return reporte

def _enviar_lote(socket, headers, client_id, lote):
    """Envía un lote de registros con un encabezado (schema, client_id, count)
       y un payload que consiste en un arreglo de arreglos de valores.
    """
    batch = {
        CABECERA: {
            ESQUEMA: headers,
            ID_CLIENTE: client_id,
            CANTIDAD: len(lote)
        },
        PAYLOAD: lote
    }
    batch_bytes = json.dumps(batch).encode("utf-8")
    msg = external_serializer.serializar_uint32(len(batch_bytes)) + batch_bytes
    socket.sendall(msg)


def _recibir_lote(socket):
    """Recibe un lote de registros con un encabezado y payload en formato compacto."""
    tamanio_lote = external_serializer.deserializar_uint32(
        _recibir_tamanio(socket, external_serializer.TAMANIO_UINT32)
    )
    batch_bytes = _recibir_tamanio(socket, tamanio_lote)
    return json.loads(batch_bytes.decode("utf-8"))


def _recibir_fin_de_registros(socket):
    size = external_serializer.deserializar_uint32(
        _recibir_tamanio(socket, external_serializer.TAMANIO_UINT32)
    )
    if size == 0:
        return None
    return _recibir_tamanio(socket, size).decode("utf-8")


MANEJADORES_RECEPCION = {
    TipoMensaje.ACK: _recibir_vacio,
    TipoMensaje.FIN_DE_REGISTROS: _recibir_fin_de_registros,
    TipoMensaje.REPORTE: _recibir_reporte,
    TipoMensaje.LOTE_TRANSACCIONES: _recibir_lote,
    TipoMensaje.LOTE_BANCOS: _recibir_lote,
    TipoMensaje.CONFIG_QUERIES: _recibir_reporte,
    TipoMensaje.HELLO: _recibir_reporte,
    TipoMensaje.ACK_RESULTADO: _recibir_reporte,
}


def recibir_mensaje(socket):
    tipo_mensaje = external_serializer.deserializar_uint32(
        _recibir_tamanio(socket, external_serializer.TAMANIO_UINT32)
    )
    manejador = MANEJADORES_RECEPCION[tipo_mensaje]
    return (tipo_mensaje, manejador(socket))


def _enviar_ack(socket):
    socket.sendall(external_serializer.serializar_uint32(TipoMensaje.ACK))


def _enviar_fin_de_registros(socket, client_id=None):
    if client_id is not None:
        client_id_bytes = client_id.encode("utf-8")
        msg = external_serializer.serializar_uint32(len(client_id_bytes)) + client_id_bytes
    else:
        msg = external_serializer.serializar_uint32(0)
    socket.sendall(msg)


def _enviar_reporte(socket, reporte):
    """Envía un reporte como string."""
    reporte_bytes = reporte.encode("utf-8")
    msg = external_serializer.serializar_uint32(len(reporte_bytes))
    msg += reporte_bytes
    socket.sendall(msg)

def _enviar_vacio(socket):
    pass

MANEJADORES_ENVIO = {
    TipoMensaje.ACK: _enviar_vacio,
    TipoMensaje.FIN_DE_REGISTROS: _enviar_fin_de_registros,
    TipoMensaje.REPORTE: _enviar_reporte,
    TipoMensaje.LOTE_TRANSACCIONES: _enviar_lote,
    TipoMensaje.LOTE_BANCOS: _enviar_lote,
    TipoMensaje.CONFIG_QUERIES: _enviar_reporte,
    TipoMensaje.HELLO: _enviar_reporte,
    TipoMensaje.ACK_RESULTADO: _enviar_reporte,
}


def enviar_mensaje(socket, tipo_mensaje, *args):
    socket.sendall(external_serializer.serializar_uint32(tipo_mensaje))
    manejador = MANEJADORES_ENVIO[tipo_mensaje]
    manejador(socket, *args)
