import logging
from common import message_protocol
from config import LOTE_SIZE


def _leer_headers_y_registros(f):
    linea_headers = f.readline().strip()
    if not linea_headers:
        return None, iter([])
    headers = linea_headers.split(",")
    registros = (linea.strip().split(",") for linea in f if linea.strip())
    return headers, registros

def enviar_archivo(filepath, tipo_mensaje, sock, lock, client_id, shutdown_event=None, ack_pendiente=None):
    logging.info(f"Enviando {filepath}...")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            headers, registros = _leer_headers_y_registros(f)
            if headers is not None:
                _enviar_lotes(headers, registros, tipo_mensaje, sock, lock, client_id, shutdown_event, ack_pendiente)
        if shutdown_event and shutdown_event.is_set():
            logging.info(f"Envío de {filepath} interrumpido.")
        else:
            logging.info(f"Envío de {filepath} completado.")
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        logging.error(f"Error de red al procesar {filepath}: {e}")
        if shutdown_event:
            shutdown_event.set()
    except Exception as e:
        logging.error(f"Error al procesar {filepath}: {e}")

def _enviar_con_prioridad_ack(sock, lock, ack_pendiente, tipo_mensaje, headers, client_id, lote):
    while True:
        if ack_pendiente:
            ack_pendiente.wait()
        with lock:
            if ack_pendiente and not ack_pendiente.is_set():
                continue
            message_protocol.external.enviar_mensaje(sock, tipo_mensaje, headers, client_id, lote)
            return

def _enviar_lotes(headers, registros, tipo_mensaje, sock, lock, client_id, shutdown_event=None, ack_pendiente=None):
    lote = []
    for registro in registros:
        if shutdown_event and shutdown_event.is_set():
            return
        lote.append(registro)
        if len(lote) >= LOTE_SIZE:
            _enviar_con_prioridad_ack(sock, lock, ack_pendiente, tipo_mensaje, headers, client_id, lote)
            lote = []
    if lote and not (shutdown_event and shutdown_event.is_set()):
        _enviar_con_prioridad_ack(sock, lock, ack_pendiente, tipo_mensaje, headers, client_id, lote)