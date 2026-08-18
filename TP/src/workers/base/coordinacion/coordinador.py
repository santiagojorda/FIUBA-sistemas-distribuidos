import threading
from common.logger import obtener_logger
from common.message_protocol.internal import ParseadorMensajes
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
    CLAVE_PROCESADOS,
    CLAVE_EMITIDOS,
    CLAVE_TOTAL_MENSAJES_ENVIADOS,
)
from .estado_cliente import EstadoClienteCoordinacion
from .hooks import HOOK_PRE_FINISHED
from .mensajes_control import msg_eof_recibido, msg_worker_finalizado, msg_barrera_completa
from .persistencia import PersistenciaCoordinacion
from .transporte import TransporteControl

logger = obtener_logger(__name__)


class CoordinadorDistribuido:
    def __init__(self, config, al_completar_sincronizacion, al_completar_barrera,
                 contador_vuelos, hooks=None, obtener_conteos_fn=None,
                 pre_flush_fn=None):
        self._config = config
        self._al_completar_sincronizacion = al_completar_sincronizacion
        self._al_completar_barrera = al_completar_barrera
        self._contador_vuelos = contador_vuelos
        self._hooks = hooks or {}
        self._obtener_conteos_fn = obtener_conteos_fn
        self._pre_flush_fn = pre_flush_fn
        self._coordinacion_lock = threading.Lock()

        self._persistencia = PersistenciaCoordinacion(
            f"coordinator_{config.prefijo_nodo}_{config.id_nodo}"
        )
        self._clientes, self._barreras_pendientes, self._worker_finished_pendientes = (
            self._persistencia.cargar(config.id_nodo, config.total_workers)
        )

        self._transporte = TransporteControl(config)

        self._evento_cierre = threading.Event()
        self._hilo_rebroadcast = threading.Thread(
            target=self._bucle_rebroadcast,
            name=f"Coordinador-Rebroadcast-{config.id_nodo}",
            daemon=True,
        )
        self._hilo_rebroadcast.start()

        self._manejadores = {
            TIPO_EOF_RECIBIDO: self._manejar_eof_recibido,
            TIPO_WORKER_FINALIZADO: self._manejar_worker_finalizado,
            TIPO_BARRERA_COMPLETA: self._manejar_barrera_completa,
        }

    def _obtener(self, client_id):
        if client_id not in self._clientes:
            self._clientes[client_id] = EstadoClienteCoordinacion()
        return self._clientes[client_id]

    def _persistir(self):
        self._persistencia.guardar(self._clientes)

    def _ejecutar_hook(self, nombre):
        hook = self._hooks.get(nombre)
        if hook:
            hook()

    def procesar_barreras_recuperadas(self):
        for cid, msg in self._barreras_pendientes:
            with self._coordinacion_lock:
                self._obtener(cid).marcar_finalizado()
                self._persistir()
                self._transporte.enviar(msg_barrera_completa(cid))
            self._al_completar_sincronizacion(cid, msg)
        self._barreras_pendientes.clear()

        for cid, originador in self._worker_finished_pendientes:
            logger.info(
                f"Reenviando {TIPO_WORKER_FINALIZADO} pendiente "
                f"para {cid} al originador {originador}."
            )
            procesados = 0
            emitidos = 0
            if self._obtener_conteos_fn:
                procesados, emitidos = self._obtener_conteos_fn(cid)
            self._transporte.enviar(
                msg_worker_finalizado(
                    cid, originador, self._config.id_nodo,
                    mensajes_procesados=procesados,
                    mensajes_emitidos=emitidos
                )
            )
        self._worker_finished_pendientes.clear()

    def registrar_eof_local(self, client_id, nombre_cola, total_esperados) -> bool:
        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            ec.eofs_locales.add(nombre_cola)
            self._persistir()
            return len(ec.eofs_locales) == total_esperados

    def limpiar_eof_local(self, client_id):
        with self._coordinacion_lock:
            ec = self._clientes.get(client_id)
            if ec is not None and ec.eofs_locales:
                ec.eofs_locales.clear()
                self._persistir()

    def marcar_eof_local_completo(self, client_id):
        with self._coordinacion_lock:
            self._obtener(client_id).eof_local_completo = True

    def esta_eof_local_completo(self, client_id) -> bool:
        with self._coordinacion_lock:
            ec = self._clientes.get(client_id)
            return ec is not None and ec.eof_local_completo

    def iniciar_barrera(self, client_id, mensaje_original):
        ejecutar_flush = False
        originador_para_flush = None

        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            ec.eof_local_completo = True

            if ec.originador is not None and self._config.tiene_cola_sharded:
                logger.info(
                    f"Barrera ya activa para {client_id} "
                    f"(originador: {ec.originador}). Disparando flush diferido."
                )
                ejecutar_flush = True
                originador_para_flush = ec.originador
            else:
                ec.originador = self._config.id_nodo
                ec.barrera_activa = True
                ec.workers_confirmados.clear()
                ec.mensaje_original = mensaje_original
                self._persistir()
                logger.info(
                    f"EOF local completo para client_id={client_id} "
                    f"(somos originador). Difundiendo control."
                )
                self._transporte.enviar(msg_eof_recibido(client_id, self._config.id_nodo))

        if ejecutar_flush:
            self._lanzar_flush_async(client_id, originador_para_flush)

    def _lanzar_flush_async(self, client_id, originador):
        threading.Thread(
            target=self._ejecutar_flush_y_notificar,
            args=(client_id, originador),
            daemon=True,
            name=f"flush-{client_id[:8]}",
        ).start()

    def _ejecutar_flush_y_notificar(self, client_id, originador):
        if self._pre_flush_fn:
            self._pre_flush_fn(client_id)
        logger.info(
            f"EOF local y de control recibidos para {client_id}. "
            f"Esperando vuelos a cero antes de flush."
        )
        self._contador_vuelos.esperar_cero(client_id)

        procesados = 0
        emitidos = 0
        if self._obtener_conteos_fn:
            procesados, emitidos = self._obtener_conteos_fn(client_id)

        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            if ec.flusheado:
                debe_flushear = False
            elif ec.flush_en_progreso:
                logger.info(
                    f"Flush en progreso para client_id={client_id}. "
                    f"Postergando {TIPO_WORKER_FINALIZADO}."
                )
                return
            else:
                debe_flushear = True
                ec.flush_en_progreso = True

        if debe_flushear:
            logger.info(
                f"Vuelos en cero para client_id={client_id}. "
                f"Flusheando datos locales."
            )
            self._al_completar_sincronizacion(client_id, None)
            with self._coordinacion_lock:
                ec = self._obtener(client_id)
                ec.flush_en_progreso = False
                ec.flusheado = True
                ec.originador_flush = originador
                self._persistir()
        else:
            logger.info(f"Ya flusheado para client_id={client_id}. Skip.")

        self._ejecutar_hook(HOOK_PRE_FINISHED)

        logger.info(
            f"Flush completo. Enviando {TIPO_WORKER_FINALIZADO} "
            f"a originator {originador}."
        )
        self._transporte.enviar(
            msg_worker_finalizado(
                client_id, originador, self._config.id_nodo,
                mensajes_procesados=procesados,
                mensajes_emitidos=emitidos
            )
        )

    def limpiar_cliente(self, client_id):
        with self._coordinacion_lock:
            self._clientes.pop(client_id, None)
        self._contador_vuelos.limpiar(client_id)
        self._persistir()

    def _procesar_mensaje_control(self, mensaje, ack, nack):
        try:
            datos = ParseadorMensajes.deserializar(mensaje)
            tipo = datos.get(TIPO_MENSAJE)
            manejador = self._manejadores.get(tipo)
            if manejador:
                manejador(datos)
        except Exception as e:
            logger.error(f"Error en control: {e}", exc_info=True)
        finally:
            ack()

    def _manejar_eof_recibido(self, datos):
        client_id = datos[ID_CLIENTE]
        originador = datos[ORIGINADOR]

        if self._cliente_ya_finalizado_o_flusheado(client_id):
            logger.info(
                f"{TIPO_EOF_RECIBIDO} recibido para cliente {client_id} "
                f"ya finalizado. Respondiendo {TIPO_WORKER_FINALIZADO}."
            )
            self._transporte.enviar(msg_worker_finalizado(client_id, originador, self._config.id_nodo))
            return

        if not self._resolver_colision_originador(client_id, originador):
            return

        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            local_completo = ec.eof_local_completo or not self._config.tiene_cola_sharded
            originador_final = ec.originador

        if local_completo:
            self._lanzar_flush_async(client_id, originador_final)
        else:
            logger.info(
                f"{TIPO_EOF_RECIBIDO} para {client_id} "
                f"(originator {originador_final}), pero el EOF local "
                f"aún no está listo. Postergando flush."
            )

    def _cliente_ya_finalizado_o_flusheado(self, client_id):
        with self._coordinacion_lock:
            ec = self._clientes.get(client_id)
            return ec is not None and (ec.finalizado or ec.flusheado)

    def _resolver_colision_originador(self, client_id, originador_nuevo):
        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            originador_actual = ec.originador

            if originador_actual is None:
                ec.originador = originador_nuevo
                return True

            if originador_nuevo == originador_actual:
                return True

            if originador_nuevo < originador_actual:
                logger.info(
                    f"Colisión de barrera: cediendo originador "
                    f"de {originador_actual} a {originador_nuevo}"
                )
                self._ceder_rol_originador(ec, originador_nuevo, originador_actual)
                return True

            logger.info(
                f"Colisión de barrera: {originador_nuevo} reclamó, "
                f"pero yo ({originador_actual}) tengo menor ID. "
                f"Reenviando mi reclamo."
            )
            self._transporte.enviar(
                msg_eof_recibido(client_id, originador_actual)
            )
            return False

    def _ceder_rol_originador(self, ec, originador_nuevo, originador_actual):
        ec.originador = originador_nuevo
        if originador_actual == self._config.id_nodo:
            ec.desactivar_barrera()
            self._persistir()

    def _manejar_worker_finalizado(self, datos):
        client_id = datos[ID_CLIENTE]
        originador = datos[ORIGINADOR]
        worker_id = datos.get(ID_WORKER)

        if originador != self._config.id_nodo:
            return

        with self._coordinacion_lock:
            ec = self._clientes.get(client_id)

            if ec is not None and ec.finalizado:
                # Si ya finalicé, no hacer rebroadcast de BARRERA_COMPLETA por cada WORKER_FINALIZADO
                # que llega tardío, para evitar inundar la red.
                return

            if ec is None or not ec.barrera_activa:
                return

            ec.workers_confirmados.add(worker_id)
            ec.worker_conteos[str(worker_id)] = {
                CLAVE_PROCESADOS: datos.get(CLAVE_MENSAJES_PROCESADOS_LOCAL, 0),
                CLAVE_EMITIDOS: datos.get(CLAVE_MENSAJES_EMITIDOS_LOCAL, 0)
            }
            confirmados = len(ec.workers_confirmados)
            logger.info(
                f"{TIPO_WORKER_FINALIZADO} para client_id={client_id}. "
                f"Confirmados: {confirmados}/{self._config.total_workers}."
            )
            self._persistir()

            if confirmados < self._config.total_workers:
                return

            msg_original = ec.mensaje_original

            total_procesados = sum(w.get(CLAVE_PROCESADOS, 0) for w in ec.worker_conteos.values())
            total_emitidos = sum(w.get(CLAVE_EMITIDOS, 0) for w in ec.worker_conteos.values())

            if msg_original:
                try:
                    payload_dict = ParseadorMensajes.deserializar(msg_original)
                    total_esperado = payload_dict.get(CLAVE_TOTAL_MENSAJES_ENVIADOS)
                    if total_esperado is not None and total_procesados != total_esperado:
                        logger.warning(
                            f"Barrera completa para {client_id} pero total procesados consolidado "
                            f"({total_procesados}) difiere de total esperado ({total_esperado})."
                        )
                except Exception as e:
                    logger.warning(f"No se pudo verificar total_mensajes_enviados en la barrera: {e}")

            ec.desactivar_barrera()
            self._persistir()

        logger.info(
            f"Barrera completa para client_id={client_id}. "
            f"Difundiendo {TIPO_BARRERA_COMPLETA}."
        )
        self._transporte.enviar(msg_barrera_completa(client_id))
        self._al_completar_sincronizacion(client_id, msg_original, total_emitidos=total_emitidos)

    def _manejar_barrera_completa(self, datos):
        client_id = datos[ID_CLIENTE]
        with self._coordinacion_lock:
            ec = self._obtener(client_id)
            if ec.finalizado:
                return
            ec.marcar_finalizado()
            self._persistir()
        logger.info(
            f"Barrera completa liberada globalmente "
            f"para client_id={client_id}."
        )
        if self._al_completar_barrera:
            self._al_completar_barrera(client_id)

    def iniciar_consumo(self):
        self._transporte.iniciar_consumo(self._procesar_mensaje_control)

    def detener_consumo(self):
        self._transporte.detener_consumo()

    def _bucle_rebroadcast(self):
        while not self._evento_cierre.wait(2.0):
            with self._coordinacion_lock:
                clientes = [
                    cid for cid, ec in self._clientes.items()
                    if ec.barrera_activa
                ]
            for client_id in clientes:
                logger.info(
                    f"Re-difundiendo {TIPO_EOF_RECIBIDO} para "
                    f"client_id={client_id} para despertar posibles "
                    f"workers reiniciados."
                )
                self._transporte.enviar(msg_eof_recibido(client_id, self._config.id_nodo))

    def cerrar(self):
        self._evento_cierre.set()
        self._transporte.cerrar()
