import hashlib
import json
import re
import threading
import uuid
from queue import Queue
from common.logger import obtener_logger
from common.crash_hook import CrashHook
from common import message_protocol, middleware
from common.constantes_protocolo import (
    CABECERA, ESQUEMA, PAYLOAD, ID_CLIENTE, ID_SOLICITUD, LOTES,
    CLAVE_QUERY, CLAVE_RESULTADO, CLAVE_EOF_REPORTE, CLAVE_COLUMNAS,
)
from config import GatewayConfig
from common import crash_points as CP

logger = obtener_logger(__name__)


class BackendListener:
    QUERY_PATTERN = r'q(\d+)'
    FIRST_GROUP = 1
    LOTE_Q4 = 500
    TIMEOUT_RECONEXION = 120

    def __init__(self, config: GatewayConfig, state):
        self.config = config
        self.state = state
        self._hook = CrashHook()
        self._processed_hashes = {}  # {client_id: set(request_ids)}
        self._q4_cuentas = {}        # {client_id: set of (bank, account)}
        self._eof_counts = {}        # {client_id: {cola_nombre: eofs_recibidos}}
        self._lock = threading.Lock()
        self._client_queues = {}     # {client_id: Queue}
        self._client_workers = {}    # {client_id: Thread}
        self._queue_lock = threading.Lock()

    def escuchar(self, cola_nombre: str):
        match = re.search(self.QUERY_PATTERN, cola_nombre)
        query_id = int(match.group(self.FIRST_GROUP)) if match else cola_nombre

        cola_entrada = middleware.MessageMiddlewareQueueRabbitMQ(self.config.mom_host, cola_nombre)
        cola_entrada.start_consuming(
            lambda body, ack, nack: self._encolar(query_id, cola_nombre, body, ack, nack)
        )

    # --- Cola serial por cliente ---

    def _encolar(self, query_id, cola_nombre, body, ack, nack):
        """
        Extrae client_id y encola el mensaje en la cola serial del cliente.
        El callback de pika retorna inmediatamente sin bloquearse.
        """
        if not self.state.servidor_corriendo:
            return nack()

        try:
            client_id = json.loads(body).get("client_id")
        except Exception:
            client_id = None

        if not client_id:
            ack()
            return

        self._obtener_o_crear_worker(client_id).put((query_id, cola_nombre, body, ack, nack))

    def _obtener_o_crear_worker(self, client_id: str) -> Queue:
        with self._queue_lock:
            if client_id not in self._client_queues:
                q = Queue()
                self._client_queues[client_id] = q
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(q,),
                    daemon=True,
                    name=f"backend-{client_id[:8]}"
                )
                self._client_workers[client_id] = t
                t.start()
            return self._client_queues[client_id]

    def _worker_loop(self, q: Queue):
        """Procesa mensajes de un cliente en orden, sin bloquear el hilo de pika."""
        while True:
            item = q.get()
            if item is None:  # centinela de parada
                break
            query_id, cola_nombre, body, ack, nack = item
            self._procesar_respuesta(query_id, cola_nombre, body, ack, nack)

    def _detener_worker(self, client_id: str):
        """Envía el centinela de parada al worker y limpia los registros."""
        with self._queue_lock:
            q = self._client_queues.pop(client_id, None)
            self._client_workers.pop(client_id, None)
        if q:
            q.put(None)

    # --- Helpers de estado ---

    def _obtener_socket_o_esperar(self, client_id, ack, nack):
        """
        Retorna (sock, lock, eof_status) si el cliente está conectado.
        Si no está pero tiene estado persistido, espera hasta TIMEOUT_RECONEXION segundos.
        Se ejecuta en el hilo worker del cliente, no en el hilo de pika.
        """
        sock, lock, eof_status = self.state.obtener_cliente(client_id)
        if sock:
            return sock, lock, eof_status

        if self.state.tiene_estado_persistido(client_id):
            logger.info(f"Cliente {client_id} no conectado, esperando reconexión (hasta {self.TIMEOUT_RECONEXION}s)...")
            self.state.esperar_cliente(client_id, timeout=self.TIMEOUT_RECONEXION)
            sock, lock, eof_status = self.state.obtener_cliente(client_id)
            if sock:
                return sock, lock, eof_status
            logger.warning(f"Timeout esperando reconexión de {client_id}, devolviendo mensaje a la cola")
            nack()
            return None, None, None

        ack()
        return None, None, None

    def _cargar_q4_si_necesario(self, client_id):
        with self._lock:
            if client_id not in self._q4_cuentas:
                estado = self.state.cargar_estado_cliente(client_id)
                cuentas_lista = estado.get("q4_cuentas", [])
                self._q4_cuentas[client_id] = set(tuple(par) for par in cuentas_lista)

    def _persistir_estado(self, client_id):
        """Guarda q4_cuentas, queries_entregadas y eof_counts_recibidos en disco."""
        with self._lock:
            q4_snapshot = set(self._q4_cuentas.get(client_id, set()))
            eof_counts_snapshot = dict(self._eof_counts[client_id]) if client_id in self._eof_counts else None

        _, _, eof_status = self.state.obtener_cliente(client_id)
        queries_entregadas = list(eof_status) if eof_status else []

        actualizaciones = {
            "q4_cuentas": [list(par) for par in q4_snapshot],
            "queries_entregadas": queries_entregadas,
        }
        if eof_counts_snapshot is not None:
            actualizaciones["eof_counts_recibidos"] = eof_counts_snapshot
        self.state.actualizar_estado_cliente(client_id, actualizaciones)

    # --- ACK de resultados ---

    TIMEOUT_ACK_RESULTADO = 30  # segundos máximos esperando que el cliente confirme recepción

    def _enviar_reporte_con_ack(self, client_id, sock, lock, payload_str):
        """
        Envía un REPORTE con batch_id y espera el ACK_RESULTADO del cliente.
        NO llama ack()/nack() a RabbitMQ — eso es responsabilidad del caller.
        Retorna True si el cliente confirmó, False si se perdió la conexión o hubo timeout.
        """
        # Usar hash del contenido como batch_id: estable entre re-entregas de RabbitMQ
        batch_id = hashlib.md5(payload_str.encode()).hexdigest()
        data = json.loads(payload_str)
        data["batch_id"] = batch_id
        payload_con_id = json.dumps(data)

        evento = self.state.registrar_ack_esperado(client_id, batch_id)
        try:
            with lock:
                message_protocol.external.enviar_mensaje(
                    sock, message_protocol.external.TipoMensaje.REPORTE, payload_con_id
                )
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.warning(f"Cliente {client_id} desconectado al enviar resultado: {e}")
            self.state.limpiar_ack(client_id, batch_id)
            return False

        if not evento.wait(timeout=self.TIMEOUT_ACK_RESULTADO):
            logger.warning(f"Timeout ACK_RESULTADO de {client_id} (batch_id={batch_id}), reencolando")
            self.state.limpiar_ack(client_id, batch_id)
            return False

        self.state.limpiar_ack(client_id, batch_id)
        return True

    # --- Procesamiento principal ---

    def _es_duplicado(self, client_id, request_id):
        if not request_id:
            return False
        with self._lock:
            if client_id not in self._processed_hashes:
                self._processed_hashes[client_id] = set()
            if request_id in self._processed_hashes[client_id]:
                return True
            self._processed_hashes[client_id].add(request_id)
        return False

    def _procesar_lotes(self, client_id, query_id, cola_nombre, sock, lock, request_id, lotes, ack, nack):
        if query_id == 4:
            self._acumular_cuentas_q4(client_id, lotes)
            self._persistir_estado(client_id)
            ack()
            return

        for batch in lotes:
            schema = batch[CABECERA][ESQUEMA]
            records = batch[PAYLOAD]
            logger.info(f"Resultado recibido para {cola_nombre} a {client_id} con {len(records)} registros.")
            resultado_lista = [
                {**dict(zip(schema, vals)), CLAVE_EOF_REPORTE: False}
                for vals in records
            ]
            payload_str = json.dumps({CLAVE_QUERY: query_id, CLAVE_RESULTADO: resultado_lista})
            if not self._enviar_reporte_con_ack(client_id, sock, lock, payload_str):
                with self._lock:
                    self._processed_hashes.pop(client_id, None)
                self.state.remover_cliente(client_id)
                nack()
                return
        ack()

    def _procesar_registro_simple(self, client_id, query_id, sock, lock, request_id, transaccion, ack, nack):
        transaccion[CLAVE_EOF_REPORTE] = False
        payload_str = json.dumps({CLAVE_QUERY: query_id, CLAVE_RESULTADO: transaccion})
        if self._enviar_reporte_con_ack(client_id, sock, lock, payload_str):
            ack()
        else:
            with self._lock:
                self._processed_hashes.pop(client_id, None)
            self.state.remover_cliente(client_id)
            nack()

    def _procesar_respuesta(self, query_id, cola_nombre, body, ack, nack):
        if not self.state.servidor_corriendo:
            return nack()

        try:
            transaccion = json.loads(body.decode("utf-8"))
            client_id = transaccion.pop(ID_CLIENTE, None)
            if not client_id:
                return ack()

            if transaccion.get("CLIENT_DISCONNECT"):
                return ack()

            estado_persistido = self.state.cargar_estado_cliente(client_id)
            if cola_nombre in set(estado_persistido.get("queries_entregadas", [])):
                logger.info(f"Query {cola_nombre} ya entregada a {client_id}, descartando")
                return ack()

            sock, lock, eof_status = self._obtener_socket_o_esperar(client_id, ack, nack)
            if not sock:
                return

            if query_id == 4:
                self._cargar_q4_si_necesario(client_id)

            if transaccion.pop("EOF", False) or transaccion.pop(CLAVE_EOF_REPORTE, False):
                self._procesar_eof(client_id, query_id, cola_nombre, sock, lock, eof_status, ack, nack)
                return

            request_id = transaccion.get(ID_SOLICITUD)
            if self._es_duplicado(client_id, request_id):
                logger.info(f"Ignorando mensaje duplicado request_id={request_id} en {cola_nombre} para {client_id}")
                return ack()

            if LOTES in transaccion:
                self._procesar_lotes(client_id, query_id, cola_nombre, sock, lock, request_id, transaccion[LOTES], ack, nack)
            else:
                self._procesar_registro_simple(client_id, query_id, sock, lock, request_id, transaccion, ack, nack)

        except json.JSONDecodeError:
            logger.error("JSON invalido")
            ack()
        except Exception as e:
            logger.error(f"Error procesando respuesta: {e}", exc_info=True)
            nack()

    def _actualizar_eof_count(self, client_id, cola_nombre, esperados):
        """Carga (si es primera vez) e incrementa el contador de EOFs. Idempotente si ya se alcanzó el total."""
        with self._lock:
            if client_id not in self._eof_counts:
                estado = self.state.cargar_estado_cliente(client_id)
                self._eof_counts[client_id] = dict(estado.get("eof_counts_recibidos", {}))
            counts = self._eof_counts[client_id]
            if counts.get(cola_nombre, 0) < esperados:
                counts[cola_nombre] = counts.get(cola_nombre, 0) + 1
            return counts[cola_nombre]

    def _finalizar_cliente(self, client_id, sock, lock):
        """Envía FIN_DE_REGISTROS y libera todo el estado en memoria y disco del cliente."""
        self._hook.verificar(CP.GW_BEFORE_FINALIZE, f"before-finalize {client_id}")
        with lock:
            message_protocol.external.enviar_mensaje(
                sock, message_protocol.external.TipoMensaje.FIN_DE_REGISTROS
            )
        with self._lock:
            self._processed_hashes.pop(client_id, None)
            self._q4_cuentas.pop(client_id, None)
            self._eof_counts.pop(client_id, None)
        self.state.limpiar_estado_cliente(client_id)
        self.state.remover_cliente(client_id)
        self._detener_worker(client_id)

    def _procesar_eof(self, client_id, query_id, cola_nombre, sock, lock, eof_status, ack, nack):
        esperados = self.config.eofs_esperados.get(cola_nombre, 1)
        recibidos = self._actualizar_eof_count(client_id, cola_nombre, esperados)
        self._persistir_estado(client_id)

        if recibidos < esperados:
            logger.info(f"EOF parcial {recibidos}/{esperados} para {cola_nombre} ({client_id})")
            return ack()

        columns_hint = None
        if query_id == 4:
            if not self._enviar_cuentas_q4(client_id, sock, lock):
                logger.warning(f"No se pudieron entregar cuentas Q4 a {client_id}, reencolando EOF")
                return nack()
            columns_hint = ["Bank", "Account"]

        self._hook.verificar(CP.GW_DOWNSTREAM_BEFORE_SEND, f"before-send-eof {client_id}")

        payload = {CLAVE_QUERY: query_id, CLAVE_RESULTADO: {CLAVE_EOF_REPORTE: True}}
        if columns_hint:
            payload[CLAVE_COLUMNAS] = columns_hint
        if not self._enviar_reporte_con_ack(client_id, sock, lock, json.dumps(payload)):
            logger.warning(f"No se pudo confirmar EOF de {cola_nombre} a {client_id}, reencolando")
            return nack()

        logger.info(f"EOF completo confirmado para {cola_nombre} a {client_id} ({recibidos}/{esperados})")
        self._hook.verificar(CP.GW_BEFORE_PERSIST_QUERY, f"before-persist-query {client_id}")
        eof_status.add(cola_nombre)
        self._persistir_estado(client_id)
        self._hook.verificar(CP.GW_AFTER_PERSIST_QUERY, f"after-persist-query {client_id}")

        if len(eof_status) == self.config.num_queries:
            logger.info(f"Todas las queries finalizadas para {client_id}")
            self._finalizar_cliente(client_id, sock, lock)

        self._hook.verificar(CP.GW_DOWNSTREAM_BEFORE_ACK, f"before-ack-eof {client_id}")
        ack()

    # --- Q4 ---

    def _acumular_cuentas_q4(self, client_id: str, batches: list):
        with self._lock:
            cuentas = self._q4_cuentas.setdefault(client_id, set())
            for batch in batches:
                schema = batch[CABECERA][ESQUEMA]
                records = batch[PAYLOAD]
                try:
                    fb_idx = schema.index("From Bank")
                    fa_idx = schema.index("From Account")
                    tb_idx = schema.index("To Bank")
                    ta_idx = schema.index("To Account")
                except ValueError as e:
                    logger.warning(f"[Q4] Schema inesperado {schema}: {e}")
                    continue
                for r in records:
                    cuentas.add((str(r[fb_idx]), str(r[fa_idx])))
                    cuentas.add((str(r[tb_idx]), str(r[ta_idx])))
            logger.info(f"[Q4] Cuentas únicas acumuladas para {client_id}: {len(cuentas)}")

    def _enviar_cuentas_q4(self, client_id: str, sock, lock):
        """Retorna True si todos los lotes fueron ACKados, False si la conexión se perdió."""
        with self._lock:
            cuentas = self._q4_cuentas.pop(client_id, set())
        registros = sorted(cuentas)
        logger.info(f"[Q4] Enviando {len(registros)} cuentas únicas a {client_id}")
        for i in range(0, max(1, len(registros)), self.LOTE_Q4):
            lote = registros[i:i + self.LOTE_Q4]
            if not lote:
                break
            resultado_lista = [{"Bank": b, "Account": a, CLAVE_EOF_REPORTE: False} for b, a in lote]
            payload_str = json.dumps({CLAVE_QUERY: 4, CLAVE_RESULTADO: resultado_lista})
            if not self._enviar_reporte_con_ack(client_id, sock, lock, payload_str):
                return False
        return True
