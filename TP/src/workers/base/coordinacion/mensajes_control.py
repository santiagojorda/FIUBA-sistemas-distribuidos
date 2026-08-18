from common.constantes_protocolo import ID_CLIENTE
from base.constantes import (
    TIPO_MENSAJE,
    TIPO_EOF_RECIBIDO,
    TIPO_WORKER_FINALIZADO,
    TIPO_BARRERA_COMPLETA,
    ORIGINADOR,
    ID_WORKER,
    CLAVE_MENSAJES_PROCESADOS_LOCAL,
    CLAVE_MENSAJES_EMITIDOS_LOCAL,
)



def msg_eof_recibido(client_id, id_nodo):
    return {
        TIPO_MENSAJE: TIPO_EOF_RECIBIDO,
        ID_CLIENTE: client_id,
        ORIGINADOR: id_nodo,
    }


def msg_worker_finalizado(client_id, originador, id_nodo, mensajes_procesados=None, mensajes_emitidos=None):
    payload = {
        TIPO_MENSAJE: TIPO_WORKER_FINALIZADO,
        ID_CLIENTE: client_id,
        ORIGINADOR: originador,
        ID_WORKER: id_nodo,
    }
    if mensajes_procesados is not None:
        payload[CLAVE_MENSAJES_PROCESADOS_LOCAL] = mensajes_procesados
    if mensajes_emitidos is not None:
        payload[CLAVE_MENSAJES_EMITIDOS_LOCAL] = mensajes_emitidos
    return payload


def msg_barrera_completa(client_id):
    return {
        TIPO_MENSAJE: TIPO_BARRERA_COMPLETA,
        ID_CLIENTE: client_id,
    }
