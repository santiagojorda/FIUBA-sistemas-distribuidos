import socket
import threading
import logging
import sys
import uuid
import time
import json
import os
from common import message_protocol
from common.constantes_protocolo import ID_CLIENTE
from common.logger import Logger
from config import SERVER_HOST, SERVER_PORT, TRANSACTIONS_FILE, ACCOUNTS_FILE, OUTPUT_DIR
from receiver import escuchar_respuesta
from sender import enviar_archivo

CLIENT_ID_SUFFIX = os.getenv('CLIENT_ID_SUFFIX', '')
CLIENT_ID_FILE = f"client_id_{CLIENT_ID_SUFFIX}.txt" if CLIENT_ID_SUFFIX else "client_id.txt"
ENVIO_COMPLETO_FILE = "envio_completo.txt"
INTENTOS_RECONEXION = 40
ESPERA_RECONEXION_SEG = 3


def main():
    Logger.configurar("client")
    inicio_cliente = time.perf_counter()

    client_id = _cargar_o_generar_client_id()

    intentos_restantes = INTENTOS_RECONEXION
    while intentos_restantes > 0:
        intentos_restantes -= 1
        resultado = _ejecutar_sesion(client_id, inicio_cliente)
        if resultado == "completado":
            break
        if resultado == "conectado_pero_fallo":
            intentos_restantes = INTENTOS_RECONEXION
        logging.info(f"Reconectando en {ESPERA_RECONEXION_SEG}s ({intentos_restantes} intentos restantes)...")
        time.sleep(ESPERA_RECONEXION_SEG)

    return 0


def _ejecutar_sesion(client_id, inicio_cliente):
    sock = _conectar_socket()
    if not sock:
        return "reintentar"

    try:
        # Handshake: el cliente se presenta primero
        hello_payload = json.dumps({"client_id": client_id})
        message_protocol.external.enviar_mensaje(sock, message_protocol.external.TipoMensaje.HELLO, hello_payload)

        tipo_mensaje, payload = message_protocol.external.recibir_mensaje(sock)
        if tipo_mensaje != message_protocol.external.TipoMensaje.CONFIG_QUERIES:
            logging.warning("Respuesta inesperada del gateway en handshake")
            return "reintentar"

        config_data = json.loads(payload)
        queries = config_data.get("queries", [])
        omitir_envio = config_data.get("omitir_envio", False)
        logging.info(f"Conectado. ID: {client_id} | Queries: {queries} | Omitir envío: {omitir_envio}")

    except Exception as e:
        logging.error(f"Error en handshake con gateway: {e}")
        _cerrar_socket(sock)
        return "reintentar"

    socket_lock = threading.Lock()
    shutdown_event = threading.Event()
    evento_completado = threading.Event()
    ack_pendiente = threading.Event()
    ack_pendiente.set()

    hilo_receptor = threading.Thread(
        target=escuchar_respuesta,
        args=(sock, queries, inicio_cliente, client_id, evento_completado, socket_lock, ack_pendiente),
        daemon=True
    )
    hilo_receptor.start()

    ya_enviado = omitir_envio

    if not ya_enviado:
        hilos_envio = _iniciar_hilos_envio(sock, socket_lock, client_id, shutdown_event, ack_pendiente)
        _esperar_envios(hilos_envio)

        if shutdown_event.is_set():
            logging.warning("Envío interrumpido por error de red, reconectando...")
            _cerrar_socket(sock)
            hilo_receptor.join(timeout=2)
            return "conectado_pero_fallo"

        try:
            _enviar_fin_registros(sock, socket_lock, client_id)
            _marcar_envio_completo(client_id)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logging.warning(f"Error enviando fin de registros: {e}, reconectando...")
            _cerrar_socket(sock)
            hilo_receptor.join(timeout=2)
            return "conectado_pero_fallo"
    else:
        logging.info("Datos ya enviados en sesión anterior, esperando resultados...")

    hilo_receptor.join()
    _cerrar_socket(sock)
    return "completado" if evento_completado.is_set() else "conectado_pero_fallo"


# --- Persistencia del client_id y estado de envío ---

def _cargar_o_generar_client_id():
    env_id = os.environ.get("CLIENT_ID")
    if env_id:
        logging.info(f"Usando client_id de variable de entorno: {env_id}")
        return env_id

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    id_path = os.path.join(OUTPUT_DIR, CLIENT_ID_FILE)
    if os.path.exists(id_path):
        with open(id_path, "r") as f:
            cid = f.read().strip()
        if cid:
            logging.info(f"Usando client_id persistido: {cid}")
            return cid
    cid = str(uuid.uuid4())
    with open(id_path, "w") as f:
        f.write(cid)
    logging.info(f"Nuevo client_id generado: {cid}")
    return cid


def _envio_ya_completado(client_id):
    path = os.path.join(OUTPUT_DIR, client_id, ENVIO_COMPLETO_FILE)
    return os.path.exists(path)


def _marcar_envio_completo(client_id):
    directorio = os.path.join(OUTPUT_DIR, client_id)
    os.makedirs(directorio, exist_ok=True)
    with open(os.path.join(directorio, ENVIO_COMPLETO_FILE), "w") as f:
        f.write("1")


# --- Helpers de red y envío ---

def _conectar_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
        return sock
    except Exception as e:
        logging.error(f"No se pudo conectar al servidor: {e}")
        sock.close()
        return None


def _iniciar_hilos_envio(sock, lock, client_id, shutdown_event, ack_pendiente=None):
    hilo_tx = threading.Thread(
        target=enviar_archivo,
        args=(TRANSACTIONS_FILE, message_protocol.external.TipoMensaje.LOTE_TRANSACCIONES, sock, lock, client_id, shutdown_event, ack_pendiente)
    )
    hilo_bancos = threading.Thread(
        target=enviar_archivo,
        args=(ACCOUNTS_FILE, message_protocol.external.TipoMensaje.LOTE_BANCOS, sock, lock, client_id, shutdown_event, ack_pendiente)
    )
    hilo_tx.start()
    hilo_bancos.start()
    return [hilo_tx, hilo_bancos]


def _esperar_envios(hilos):
    for h in hilos:
        h.join()


def _enviar_fin_registros(sock, lock, client_id):
    with lock:
        message_protocol.external.enviar_mensaje(
            sock,
            message_protocol.external.TipoMensaje.FIN_DE_REGISTROS,
            client_id
        )


def _cerrar_socket(sock):
    try:
        sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
