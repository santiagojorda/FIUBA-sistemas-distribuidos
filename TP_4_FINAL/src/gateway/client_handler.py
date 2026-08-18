import socket
import uuid
import json
import gc
import ctypes
from common.logger import obtener_logger
from common.crash_hook import CrashHook
from common import message_protocol, middleware, sharding
from common import crash_points as CP
from common.constantes_protocolo import (
    CABECERA, ESQUEMA, PAYLOAD, ID_CLIENTE, ID_SOLICITUD, LOTES, CANTIDAD,
    FIN_DE_ARCHIVO, DESCONEXION_CLIENTE, ID_SESION,
    CONF_PREFIJO_SHARD, CONF_TOTAL_WORKERS, CONF_CAMPO_HASH,
)
from config import GatewayConfig

logger = obtener_logger(__name__)


class ClientHandler:
    FIRST_ELEMENT = 0

    def __init__(self, config: GatewayConfig, state):
        self.config = config
        self.state = state
        self._hook = CrashHook()

    def atender(self, client_socket):
        client_id = self._leer_hello(client_socket)
        if not client_id:
            client_socket.close()
            return

        estado = self.state.cargar_estado_cliente(client_id)
        datos_ya_enviados = estado.get("datos_enviados", False)
        queries_ya_entregadas = set(estado.get("queries_entregadas", []))

        logger.info(f"Cliente {client_id} conectado (datos_enviados={datos_ya_enviados}, queries_entregadas={queries_ya_entregadas})")

        self.state.registrar_cliente(client_id, client_socket)

        # Adquirir el lock antes de enviar CONFIG_QUERIES: evita que el BackendListener
        # empiece a enviar REPORTEs al socket antes de que el cliente haya recibido CONFIG_QUERIES.
        _, lock, eof_status = self.state.obtener_cliente(client_id)
        with lock:
            if queries_ya_entregadas and eof_status is not None:
                eof_status.update(queries_ya_entregadas)
            self._enviar_config(client_socket, client_id, datos_ya_enviados)

        if datos_ya_enviados:
            saved_session = estado.get("session_id")
            if saved_session:
                self.state.registrar_sesion(client_id, saved_session)
            if len(queries_ya_entregadas) >= len(self._obtener_lista_queries()):
                logger.info(f"Cliente {client_id}: todas las queries ya entregadas, enviando FIN_DE_REGISTROS")
                try:
                    with lock:
                        message_protocol.external.enviar_mensaje(
                            client_socket, message_protocol.external.TipoMensaje.FIN_DE_REGISTROS
                        )
                except Exception as e:
                    logger.warning(f"Error enviando FIN_DE_REGISTROS a {client_id}: {e}")
                self.state.limpiar_estado_cliente(client_id)
                self.state.remover_cliente(client_id)
                client_socket.close()
                return
            self._modo_solo_resultados(client_id, client_socket)
        else:
            self._modo_normal(client_id, client_socket)

    def _leer_hello(self, client_socket):
        """Lee el mensaje HELLO del cliente y retorna el client_id (nuevo o existente)."""
        try:
            tipo_mensaje, payload = message_protocol.external.recibir_mensaje(client_socket)
            if tipo_mensaje == message_protocol.external.TipoMensaje.HELLO:
                data = json.loads(payload)
                cid = data.get("client_id", "").strip()
                if cid:
                    logger.info(f"Cliente reconectando con ID existente: {cid}")
                    return cid
                nuevo_id = str(uuid.uuid4())
                logger.info(f"Nuevo cliente, asignando ID: {nuevo_id}")
                return nuevo_id
        except Exception as e:
            logger.error(f"Error leyendo HELLO del cliente: {e}")
        return None

    def _obtener_lista_queries(self):
        queries = []
        for q in self.config.input_queues:
            try:
                queries.append(int(q.split('_')[0][1:]))
            except (IndexError, ValueError):
                pass
        queries.sort()
        return queries

    def _enviar_config(self, client_socket, client_id, omitir_envio):
        try:
            config_payload = json.dumps({
                "queries": self._obtener_lista_queries(),
                "client_id": client_id,
                "omitir_envio": omitir_envio,
            })
            message_protocol.external.enviar_mensaje(
                client_socket, message_protocol.external.TipoMensaje.CONFIG_QUERIES, config_payload
            )
        except Exception as e:
            logger.error(f"Error enviando CONFIG_QUERIES a {client_id}: {e}")

    def _leer_acks(self, client_id, client_socket):
        """Lee ACK_RESULTADO del cliente y los despacha al BackendListener vía state."""
        try:
            while True:
                tipo_mensaje, payload = message_protocol.external.recibir_mensaje(client_socket)
                if tipo_mensaje == message_protocol.external.TipoMensaje.ACK_RESULTADO:
                    data = json.loads(payload)
                    self.state.notificar_ack(client_id, data.get("batch_id"))
        except Exception:
            pass
        finally:
            self.state.cancelar_acks_cliente(client_id)
            try:
                client_socket.close()
            except Exception:
                pass
            gc.collect()
            try:
                ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
            except Exception:
                pass

    def _modo_solo_resultados(self, client_id, client_socket):
        """
        El cliente ya envió todos sus datos en una sesión anterior.
        Solo esperamos a que BackendListener termine de entregar los resultados
        y el cliente cierre la conexión.
        """
        logger.info(f"Cliente {client_id} en modo solo-resultados")
        self._leer_acks(client_id, client_socket)

    def _modo_normal(self, client_id, client_socket):
        """Recibe lotes del cliente, los publica en RabbitMQ y espera el END_OF_RECORDS."""
        colas_tx = [middleware.MessageMiddlewareQueueRabbitMQ(self.config.mom_host, q) for q in self.config.output_queues]
        colas_bancos = {}

        if self.config.bank_queue_config:
            prefix = self.config.bank_queue_config.get(CONF_PREFIJO_SHARD)
            total_workers = self.config.bank_queue_config.get(CONF_TOTAL_WORKERS, self.config.DEFAULT_WORKERS)
            for i in range(1, total_workers + 1):
                colas_bancos[i] = middleware.MessageMiddlewareQueueRabbitMQ(self.config.mom_host, f"{prefix}_{i}")

        estado_previo = self.state.cargar_estado_cliente(client_id)
        if estado_previo.get("conectado"):
            sesion_vieja = estado_previo.get("session_id")
            logger.info(f"Cliente {client_id} reconectando — enviando DISCONNECT por colas de datos (sesión {sesion_vieja})")
            self._enviar_disconnect(client_id, colas_tx, colas_bancos, sesion_vieja)

        self._hook.verificar(CP.GW_BEFORE_PERSIST_CONNECTED, f"pre-conectado {client_id}")

        session_id = str(uuid.uuid4())[:8]
        self.state.registrar_sesion(client_id, session_id)
        self.state.actualizar_estado_cliente(client_id, {"conectado": True, "session_id": session_id})
        logger.info(f"Cliente {client_id} sesión {session_id} iniciada")

        self._hook.verificar(CP.GW_AFTER_PERSIST_CONNECTED, f"post-conectado {client_id}")

        eof_enviado = False
        try:
            while True:
                tipo_mensaje, payload = message_protocol.external.recibir_mensaje(client_socket)

                if tipo_mensaje == message_protocol.external.TipoMensaje.LOTE_TRANSACCIONES:
                    self._reenviar_lote_tx(client_id, client_socket, payload, colas_tx)

                elif tipo_mensaje == message_protocol.external.TipoMensaje.LOTE_BANCOS:
                    self._reenviar_lote_bancos(client_id, client_socket, payload, colas_bancos)

                elif tipo_mensaje == message_protocol.external.TipoMensaje.ACK_RESULTADO:
                    # El backend ya comenzó a mandar resultados mientras el cliente aún enviaba datos
                    data = json.loads(payload)
                    self.state.notificar_ack(client_id, data.get("batch_id"))

                elif tipo_mensaje == message_protocol.external.TipoMensaje.FIN_DE_REGISTROS:
                    if client_id is None:
                        client_id = payload or str(uuid.uuid4())
                        self.state.registrar_cliente(client_id, client_socket)
                        logger.info(f"Cliente {client_id} conectado (FIN_DE_REGISTROS)")

                    eof_msg = json.dumps({ID_CLIENTE: client_id, FIN_DE_ARCHIVO: True}).encode("utf-8")
                    for q in colas_tx:
                        q.send(eof_msg)
                    for q in colas_bancos.values():
                        q.send(eof_msg)
                    eof_enviado = True
                    logger.info(f"EOF enviado para {client_id}")

                    self._hook.verificar(CP.GW_BEFORE_PERSIST_DATOS_ENVIADOS, f"pre-datos_enviados {client_id}")
                    self.state.actualizar_estado_cliente(client_id, {"datos_enviados": True, "session_id": session_id})
                    self._hook.verificar(CP.GW_AFTER_PERSIST_DATOS_ENVIADOS, f"post-datos_enviados {client_id}")
                    break

        except socket.error:
            logger.warning(f"Cliente {client_id} desconectado abruptamente")
        except Exception as e:
            logger.error(f"Error con cliente {client_id}: {e}", exc_info=True)
        finally:
            if not eof_enviado:
                sesion_actual = self.state.obtener_sesion(client_id)
                self._enviar_disconnect(client_id, colas_tx, colas_bancos, sesion_actual)
                self.state.remover_cliente(client_id)
            for q in colas_tx:
                q.close()
            for q in colas_bancos.values():
                q.close()

        if eof_enviado:
            # Datos enviados al sistema — ahora esperamos ACKs de resultados del cliente
            self._leer_acks(client_id, client_socket)
        else:
            gc.collect()
            try:
                ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
            except Exception:
                pass

    def _reenviar_lote_tx(self, client_id, client_socket, payload, colas_tx):
        header = payload[CABECERA]
        schema = self._deduplicar_schema(header[ESQUEMA])
        header[ESQUEMA] = schema
        records = payload[PAYLOAD]

        for q in colas_tx:
            req_id = self.state.generar_request_id(client_id, q.queue_name)
            internal_msg = json.dumps({
                ID_CLIENTE: client_id,
                ID_SOLICITUD: req_id,
                LOTES: [{CABECERA: header, PAYLOAD: records}]
            }).encode("utf-8")
            q.send(internal_msg)

        self._hook.verificar(CP.GW_UPSTREAM_BEFORE_ACK, f"upstream {client_id}")
        _, lock, _ = self.state.obtener_cliente(client_id)
        if lock:
            with lock:
                message_protocol.external.enviar_mensaje(client_socket, message_protocol.external.TipoMensaje.ACK)

    def _reenviar_lote_bancos(self, client_id, client_socket, payload, colas_bancos):
        if not self.config.bank_queue_config:
            _, lock, _ = self.state.obtener_cliente(client_id)
            if lock:
                with lock:
                    message_protocol.external.enviar_mensaje(client_socket, message_protocol.external.TipoMensaje.ACK)
            return

        header = payload[CABECERA]
        schema = self._deduplicar_schema(header[ESQUEMA])
        header[ESQUEMA] = schema
        records = payload[PAYLOAD]

        hash_field = self.config.bank_queue_config.get(CONF_CAMPO_HASH, "Bank ID")
        total_workers = self.config.bank_queue_config.get(CONF_TOTAL_WORKERS, 1)
        hash_idx = schema.index(hash_field) if hash_field in schema else None

        records_by_shard = {}
        for record_values in records:
            bank_val = record_values[hash_idx] if hash_idx is not None else "default"
            shard_id = sharding.obtener_id_shard(bank_val, total_workers)
            records_by_shard.setdefault(shard_id, []).append(record_values)

        for shard_id, shard_records in records_by_shard.items():
            req_id = self.state.generar_request_id(client_id, colas_bancos[shard_id].queue_name)
            shard_batch = json.dumps({
                ID_CLIENTE: client_id,
                ID_SOLICITUD: req_id,
                LOTES: [{
                    CABECERA: {ESQUEMA: schema, ID_CLIENTE: client_id, CANTIDAD: len(shard_records)},
                    PAYLOAD: shard_records
                }]
            }).encode("utf-8")
            colas_bancos[shard_id].send(shard_batch)

        self._hook.verificar(CP.GW_UPSTREAM_BEFORE_ACK, f"upstream {client_id}")
        _, lock, _ = self.state.obtener_cliente(client_id)
        if lock:
            with lock:
                message_protocol.external.enviar_mensaje(client_socket, message_protocol.external.TipoMensaje.ACK)

    @staticmethod
    def _deduplicar_schema(schema):
        limpio = []
        counts = {}
        for col in schema:
            if col in counts:
                counts[col] += 1
                limpio.append(f"{col}.{counts[col]}")
            else:
                counts[col] = 0
                limpio.append(col)
        return limpio

    def _enviar_disconnect(self, client_id, colas_tx, colas_bancos, session_id=None):
        payload = {ID_CLIENTE: client_id, DESCONEXION_CLIENTE: True}
        if session_id:
            payload[ID_SESION] = session_id
        disconnect_msg = json.dumps(payload).encode("utf-8")
        logger.info(f"Enviando CLIENT_DISCONNECT para {client_id}")
        for q in colas_tx:
            try:
                q.send(disconnect_msg)
            except Exception as e:
                logger.warning(f"No se pudo enviar CLIENT_DISCONNECT a cola tx: {e}")
        for q in colas_bancos.values():
            try:
                q.send(disconnect_msg)
            except Exception as e:
                logger.warning(f"No se pudo enviar CLIENT_DISCONNECT a cola bancos: {e}")
