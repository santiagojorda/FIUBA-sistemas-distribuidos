import json
import random
import threading
import time

from common.logger import obtener_logger
from common.crash_hook import CrashHook
from common import crash_points as CP
from common.persistencia import PersistidorEstado
from common.middleware.middleware_rabbitmq import (
    FanoutExchangeRabbitMQ,
    FanoutQueueRabbitMQ,
    MessageMiddlewareQueueRabbitMQ,
)

EXCHANGE_LATIDO_LIDER = "heartbeat.watchdog"


class EleccionAnillo:

    def __init__(self, config, al_ser_lider, al_perder_liderazgo, al_caer_standby=None, al_registrar_nodo=None):
        self._config = config
        self._al_ser_lider = al_ser_lider
        self._al_perder_liderazgo = al_perder_liderazgo
        self._al_caer_standby = al_caer_standby
        self._al_registrar_nodo = al_registrar_nodo

        self._id = config.id_watchdog
        self._n = config.cantidad_watchdogs
        self._id_siguiente = (self._id % self._n) + 1
        self._logger = obtener_logger(f"Anillo-{self._id}")
        self._hook = CrashHook("/tmp")

        self._es_lider = False
        self._id_lider = None
        self._en_eleccion = False
        self._eleccion_iniciada_en: float | None = None
        self._ultimo_latido_lider: float | None = None
        self._ultimo_destino_eleccion: int | None = None
        self._coordinadores_reenviados: set[int] = set()
        self._ids_sospechados_caidos: dict[int, float] = {}

        self._lider_desde: float | None = None
        self._ultimo_visto_standby: dict[int, float] = {}
        self._standbys_caidos_reportados: set[int] = set()

        self._lock = threading.Lock()
        self._lock_envio = threading.Lock()
        self._evento_parada = threading.Event()

        self._topologia = {}
        self._lock_topologia = threading.Lock()
        self._persistidor_topologia = PersistidorEstado("topologia")
        self._cargar_topologia_de_disco()

        self._consumidor_anillo: MessageMiddlewareQueueRabbitMQ | None = None
        self._emisores_anillo: dict[int, MessageMiddlewareQueueRabbitMQ] = {}
        self._consumidor_latidos: FanoutQueueRabbitMQ | None = None
        self._publicador_latidos: FanoutExchangeRabbitMQ | None = None

    def iniciar(self):
        threading.Thread(target=self._consumir_anillo, daemon=True, name=f"anillo-{self._id}").start()
        threading.Thread(target=self._consumir_latido_lider, daemon=True, name=f"anillo-hb-{self._id}").start()
        threading.Thread(target=self._bucle_periodico, daemon=True, name=f"anillo-periodico-{self._id}").start()
        threading.Thread(target=self._chequeo_inicial, daemon=True, name=f"anillo-init-{self._id}").start()
        threading.Thread(target=self._consumir_registro_topologia, daemon=True, name=f"anillo-reg-{self._id}").start()
        self._logger.info(
            f"Iniciado. Siguiente en anillo: watchdog_{self._id_siguiente}. "
            f"Total nodos: {self._n}"
        )

    def _cargar_topologia_de_disco(self):
        estado = self._persistidor_topologia.cargar()
        if estado:
            with self._lock_topologia:
                for etapa, instancias in estado.items():
                    self._topologia[etapa] = set(f"{int(i):02d}" if str(i).isdigit() else str(i) for i in instancias)
            self._logger.info(f"Topología cargada de disco: {len(estado)} etapas.")
            self._hook.verificar(CP.WD_POST_TOPOLOGY_LOAD, f"post-load watchdog_{self._id}")

    def _guardar_topologia_a_disco(self):
        serializable = {etapa: list(instancias) for etapa, instancias in self._topologia.items()}
        self._persistidor_topologia.guardar(serializable)
        self._hook.verificar(CP.WD_POST_TOPOLOGY_SAVE, f"post-save watchdog_{self._id}")

    def obtener_topologia_serializable(self):
        with self._lock_topologia:
            return {etapa: list(instancias) for etapa, instancias in self._topologia.items()}

    def _fusionar_topologia(self, otra_topologia):
        if not otra_topologia:
            return
        hubo_cambio = False
        with self._lock_topologia:
            for etapa, instancias in otra_topologia.items():
                if etapa not in self._topologia:
                    self._topologia[etapa] = set()
                    hubo_cambio = True
                nuevos = set(f"{int(inst):02d}" if str(inst).isdigit() else str(inst) for inst in instancias)
                if not nuevos.issubset(self._topologia[etapa]):
                    self._topologia[etapa].update(nuevos)
                    hubo_cambio = True
            if hubo_cambio:
                self._guardar_topologia_a_disco()

    def _consumir_registro_topologia(self):
        nombre_cola = f"watchdog.registro.{self._id}"

        def al_recibir_registro(msg: bytes, ack, _):
            try:
                payload = json.loads(msg.decode("utf-8"))
                etapa = payload.get("etapa")
                instancia = payload.get("instancia")
                if etapa and instancia:
                    hubo_cambio = False
                    with self._lock_topologia:
                        if etapa not in self._topologia:
                            self._topologia[etapa] = set()
                        raw = str(instancia)
                        inst_str = f"{int(raw):02d}" if raw.isdigit() else raw
                        if inst_str not in self._topologia[etapa]:
                            self._topologia[etapa].add(inst_str)
                            hubo_cambio = True
                        if hubo_cambio:
                            self._guardar_topologia_a_disco()
                    self._logger.info(f"Registro dinámico recibido: {etapa}/{instancia}")
                    if hubo_cambio and self._al_registrar_nodo:
                        self._al_registrar_nodo(etapa, inst_str)
                ack()
            except Exception as e:
                self._logger.warning(f"Error procesando registro de topología: {e}")
                ack()

        while not self._evento_parada.is_set():
            try:
                cola = FanoutQueueRabbitMQ(self._config.host_mom, nombre_cola, "watchdog.exchange.registro")
                self._logger.info(f"Escuchando registros de topología en {nombre_cola}")
                cola.start_consuming(al_recibir_registro)
            except Exception as e:
                if self._evento_parada.is_set():
                    return
                self._logger.error(f"Error en consumo de registros de topología: {e}. Reconectando en 2s...")
                self._evento_parada.wait(2)

    def detener(self):
        self._evento_parada.set()
        for cola in [self._consumidor_anillo, self._consumidor_latidos]:
            if cola:
                try:
                    cola.stop_consuming()
                except Exception:
                    pass

    def _chequeo_inicial(self):
        demora = random.uniform(0, self._config.demora_inicial_eleccion_max)
        self._logger.info(f"Esperando {demora:.1f}s antes de verificar líder.")
        if self._evento_parada.wait(demora):
            return

        with self._lock:
            latido_recibido = self._ultimo_latido_lider is not None

        if latido_recibido:
            self._logger.info(f"Líder activo detectado. Anunciando presencia al anillo.")
            self._anunciar_vivo()
        else:
            self._logger.info(f"Sin heartbeat de líder. Iniciando elección.")
            self._iniciar_eleccion()

    def _anunciar_vivo(self):
        msg = {"tipo": "vivo", "id": self._id, "topologia": self.obtener_topologia_serializable()}
        for nid in range(1, self._n + 1):
            if nid != self._id:
                self._enviar_a(nid, msg)
        self._logger.info(f"Anuncio 'vivo' enviado a todos los nodos.")

    def _manejar_vivo(self, id_nodo: int):
        with self._lock:
            self._ids_sospechados_caidos.pop(id_nodo, None)
            if self._es_lider:
                self._ultimo_visto_standby[id_nodo] = time.time()
                self._standbys_caidos_reportados.discard(id_nodo)
        self._logger.info(f"watchdog_{id_nodo} anunció que está vivo → removido de sospechados.")

    def _iniciar_eleccion(self):
        with self._lock:
            if self._en_eleccion:
                transcurrido = (
                    time.time() - self._eleccion_iniciada_en
                    if self._eleccion_iniciada_en is not None
                    else 0
                )
                if transcurrido < self._config.timeout_eleccion:
                    return
                if (self._ultimo_destino_eleccion is not None
                         and self._ultimo_destino_eleccion != self._id):
                    self._ids_sospechados_caidos.setdefault(self._ultimo_destino_eleccion, time.time())
                    self._logger.warning(
                        f"Timeout de elección: "
                        f"watchdog_{self._ultimo_destino_eleccion} agregado a sospechados."
                    )
                self._logger.warning(
                    f"Elección sin resultado tras {transcurrido:.0f}s. "
                    "Reintentando saltando nodos sospechados."
                )
            self._en_eleccion = True
            self._eleccion_iniciada_en = time.time()
            saltar = list(self._ids_sospechados_caidos)

        destino = self._obtener_proximo_destino()
        with self._lock:
            self._ultimo_destino_eleccion = destino
        self._logger.info(f"Elección iniciada — enviando id={self._id} a watchdog_{destino} (saltar={saltar}).")
        self._enviar_a(destino, {"tipo": "eleccion", "id": self._id, "skip": saltar, "topologia": self.obtener_topologia_serializable()})

    def _manejar_eleccion(self, id_recibido: int, saltar: list[int]):
        with self._lock:
            if saltar:
                ahora = time.time()
                for nid in saltar:
                    self._ids_sospechados_caidos.setdefault(nid, ahora)
            es_lider = self._es_lider
            id_lider = self._id_lider
            ultimo_latido = self._ultimo_latido_lider

        id_maximo = max(id_recibido, self._id)

        if id_recibido == self._id:
            if es_lider:
                self._logger.debug(f"Ya soy líder, ignorando elección duplicada.")
                return
            if (id_lider is not None
                    and id_lider != self._id
                    and ultimo_latido is not None
                    and time.time() - ultimo_latido < self._config.timeout_lider_segundos):
                self._logger.info(
                    f"Ignorando elección propia: watchdog_{id_lider} ya es líder activo."
                )
                return
            self._declarar_lider()
        else:
            if es_lider:
                self._logger.debug(f"Soy líder, absorbiendo mensaje de elección.")
                return
            if (id_lider is not None
                    and ultimo_latido is not None
                    and time.time() - ultimo_latido < self._config.timeout_lider_segundos):
                self._logger.debug(f"Líder activo conocido, absorbiendo elección.")
                return
            with self._lock:
                self._en_eleccion = True
                saltar_actual = list(self._ids_sospechados_caidos)
            destino = self._obtener_proximo_destino()
            self._logger.info(
                f"Reenviando elección id={id_maximo} "
                f"(recibido={id_recibido}) → watchdog_{destino} (saltar={saltar_actual})."
            )
            self._enviar_a(destino, {"tipo": "eleccion", "id": id_maximo, "skip": saltar_actual, "topologia": self.obtener_topologia_serializable()})

    def _declarar_lider(self):
        with self._lock:
            if self._es_lider:
                self._logger.debug(f"Ya soy líder, ignorando declaración duplicada.")
                return
            self._es_lider = True
            self._id_lider = self._id
            self._en_eleccion = False
            self._eleccion_iniciada_en = None
            self._coordinadores_reenviados.clear()
            destino_coordinador = self._calcular_proximo_destino()
            self._ids_sospechados_caidos.pop(self._id, None)
            ahora = time.time()
            nodos_caidos = [
                nid for nid, ts in self._ids_sospechados_caidos.items()
                if ahora - ts < self._config.ttl_sospechados_caidos
            ]
            self._lider_desde = ahora
            self._ultimo_visto_standby.clear()
            self._standbys_caidos_reportados.clear()

        self._logger.info(f"¡SOY EL LÍDER! Nodos caídos detectados: {nodos_caidos}")
        self._al_ser_lider(nodos_caidos)

        self._hook.verificar(CP.LEADER_MID_ELECTION, f"mid-election watchdog_{self._id}")
        self._hook.verificar(CP.WD_POST_LEADER_DECLARE, f"post-leader watchdog_{self._id}")

        self._enviar_a(destino_coordinador, {"tipo": "coordinador", "id": self._id, "topologia": self.obtener_topologia_serializable()})
        threading.Thread(
            target=self._bucle_latido_lider, daemon=True, name=f"anillo-hb-envio-{self._id}"
        ).start()

    def _manejar_coordinador(self, id_lider: int):
        if id_lider == self._id:
            with self._lock:
                if not self._es_lider:
                    self._logger.debug(
                        "Coordinador con id propio pero no soy líder — mensaje obsoleto."
                    )
            return

        with self._lock:
            ya_reenviado = id_lider in self._coordinadores_reenviados
            if not ya_reenviado:
                self._coordinadores_reenviados.add(id_lider)
            self._id_lider = id_lider
            self._ultimo_latido_lider = time.time()
            self._en_eleccion = False
            self._eleccion_iniciada_en = None
            self._ids_sospechados_caidos.pop(id_lider, None)
            era_lider = self._es_lider
            self._es_lider = False
            if era_lider:
                self._lider_desde = None
                self._ultimo_visto_standby.clear()
                self._standbys_caidos_reportados.clear()

        self._logger.info(f"Líder establecido: watchdog_{id_lider}")

        if era_lider:
            self._al_perder_liderazgo()

        if not ya_reenviado:
            destino = self._obtener_proximo_destino()
            self._enviar_a(destino, {"tipo": "coordinador", "id": id_lider, "topologia": self.obtener_topologia_serializable()})

    def _consumir_anillo(self):
        nombre_cola = f"ring.{self._id}"
        while not self._evento_parada.is_set():
            try:
                cola = MessageMiddlewareQueueRabbitMQ(self._config.host_mom, nombre_cola)
                self._consumidor_anillo = cola
                self._logger.info(f"Escuchando cola {nombre_cola}")
                cola.start_consuming(self._al_recibir_mensaje_anillo)
            except Exception as e:
                if self._evento_parada.is_set():
                    return
                self._logger.error(f"Error en cola {nombre_cola}: {e}. Reconectando en 2s...")
                self._evento_parada.wait(2)

    def _al_recibir_mensaje_anillo(self, msg: bytes, ack, nack):
        try:
            payload = json.loads(msg.decode("utf-8"))
            self._fusionar_topologia(payload.get("topologia"))
            tipo = payload.get("tipo")
            id_recibido = payload.get("id")
            saltar = payload.get("skip", [])
            ack()
            if tipo == "eleccion":
                self._manejar_eleccion(id_recibido, saltar)
            elif tipo == "coordinador":
                self._manejar_coordinador(id_recibido)
            elif tipo == "vivo":
                self._manejar_vivo(id_recibido)
            elif tipo == "hb_standby":
                self._manejar_latido_standby(id_recibido)
            else:
                self._logger.warning(f"Tipo de mensaje desconocido: {tipo}")
        except Exception as e:
            self._logger.warning(f"Mensaje de anillo malformado: {e}")
            ack()

    def _bucle_latido_lider(self):
        try:
            pub = FanoutExchangeRabbitMQ(self._config.host_mom, EXCHANGE_LATIDO_LIDER)
            self._publicador_latidos = pub
            while not self._evento_parada.is_set():
                with self._lock:
                    if not self._es_lider:
                        break
                hb = json.dumps({"tipo": "lider_hb", "id": self._id, "timestamp": time.time(), "topologia": self.obtener_topologia_serializable()}).encode()
                try:
                    pub.send(hb)
                    self._logger.debug(f"Heartbeat de líder enviado.")
                except Exception as e:
                    self._logger.warning(f"Error enviando heartbeat de líder: {e}")
                self._evento_parada.wait(self._config.intervalo_latido_lider)
        except Exception as e:
            if not self._evento_parada.is_set():
                self._logger.error(f" Error en loop heartbeat líder: {e}", exc_info=True)

    def _consumir_latido_lider(self):
        nombre_cola = f"heartbeat.watchdog.{self._id}"
        while not self._evento_parada.is_set():
            try:
                cola = FanoutQueueRabbitMQ(self._config.host_mom, nombre_cola, EXCHANGE_LATIDO_LIDER)
                self._consumidor_latidos = cola
                self._logger.info(f"Monitoreando heartbeats de líder en {nombre_cola}")
                cola.start_consuming(self._al_recibir_latido_lider)
            except Exception as e:
                if self._evento_parada.is_set():
                    return
                self._logger.error(f"Error monitoreando heartbeat líder: {e}. Reconectando en 2s...")
                self._evento_parada.wait(2)

    def _al_recibir_latido_lider(self, msg: bytes, ack, _):
        try:
            payload = json.loads(msg.decode("utf-8"))
            self._fusionar_topologia(payload.get("topologia"))
            id_lider = payload.get("id")
            with self._lock:
                self._ultimo_latido_lider = time.time()
                if not self._es_lider and id_lider is not None:
                    self._id_lider = id_lider
                    self._ids_sospechados_caidos.pop(id_lider, None)
            self._logger.debug(f"Heartbeat recibido de líder watchdog_{id_lider}.")
            ack()
        except Exception as e:
            self._logger.warning(f"Heartbeat de líder malformado: {e}")
            ack()

    def _bucle_periodico(self):
        tiempo_inicio = time.time()
        while not self._evento_parada.wait(self._config.intervalo_chequeo_lider):
            self._tick_timeout_lider(tiempo_inicio)
            self._tick_latido_standby()
            self._tick_chequeo_standbys()

    def _tick_timeout_lider(self, tiempo_inicio: float):
        with self._lock:
            if self._es_lider:
                return
            ultimo_latido = self._ultimo_latido_lider
            lider_caido = self._id_lider
            en_eleccion = self._en_eleccion
            eleccion_iniciada = self._eleccion_iniciada_en

        transcurrido = time.time() - ultimo_latido if ultimo_latido is not None else time.time() - tiempo_inicio

        if transcurrido <= self._config.timeout_lider_segundos:
            return

        eleccion_expirada = (
            en_eleccion
            and eleccion_iniciada is not None
            and time.time() - eleccion_iniciada >= self._config.timeout_eleccion
        )
        if en_eleccion and not eleccion_expirada:
            return

        with self._lock:
            if lider_caido is not None:
                self._ids_sospechados_caidos[lider_caido] = time.time()
            self._id_lider = None
            self._ultimo_latido_lider = None
            self._coordinadores_reenviados.clear()

        self._logger.warning(f"Sin heartbeat de líder por {transcurrido:.1f}s. Iniciando nueva elección.")
        self._iniciar_eleccion()

    def _tick_latido_standby(self):
        with self._lock:
            es_lider = self._es_lider
            id_lider = self._id_lider
        if not es_lider and id_lider is not None:
            try:
                self._enviar_a(id_lider, {"tipo": "hb_standby", "id": self._id})
                self._logger.debug(f"Heartbeat de standby enviado al líder watchdog_{id_lider}.")
            except Exception as e:
                self._logger.warning(f"Error enviando heartbeat de standby: {e}")

    def _tick_chequeo_standbys(self):
        with self._lock:
            if not self._es_lider or self._lider_desde is None:
                return
            ahora = time.time()
            if ahora - self._lider_desde < self._config.timeout_lider_segundos:
                return
            caidos = []
            for nid in range(1, self._n + 1):
                if nid == self._id or nid in self._standbys_caidos_reportados:
                    continue
                ultimo_ts = self._ultimo_visto_standby.get(nid)
                if ultimo_ts is None or ahora - ultimo_ts > self._config.timeout_lider_segundos:
                    caidos.append(nid)
                    self._standbys_caidos_reportados.add(nid)

        for nid in caidos:
            self._logger.warning(f"Standby watchdog_{nid} sin heartbeat. Publicando caída.")
            if self._al_caer_standby is not None:
                self._al_caer_standby(nid)

    def _manejar_latido_standby(self, id_nodo: int):
        with self._lock:
            if not self._es_lider:
                return
            self._ultimo_visto_standby[id_nodo] = time.time()
            self._standbys_caidos_reportados.discard(id_nodo)
        self._logger.debug(f"Heartbeat de standby recibido de watchdog_{id_nodo}.")

    def _calcular_proximo_destino(self) -> int:
        ahora = time.time()
        muertos = {
            nid for nid, ts in self._ids_sospechados_caidos.items()
            if ahora - ts < self._config.ttl_sospechados_caidos
        }
        destino = self._id_siguiente
        for _ in range(self._n):
            if destino not in muertos:
                return destino
            destino = (destino % self._n) + 1
        return self._id_siguiente

    def _obtener_proximo_destino(self) -> int:
        with self._lock:
            return self._calcular_proximo_destino()

    def _enviar_a(self, id_destino: int, payload: dict):
        nombre_cola = f"ring.{id_destino}"
        datos = json.dumps(payload).encode()
        with self._lock_envio:
            try:
                if id_destino not in self._emisores_anillo:
                    self._emisores_anillo[id_destino] = MessageMiddlewareQueueRabbitMQ(
                        self._config.host_mom, nombre_cola
                    )
                self._emisores_anillo[id_destino].send(datos)
            except Exception as e:
                self._logger.error(
                    f"Error enviando {payload.get('tipo')} a {nombre_cola}: {e}",
                    exc_info=True,
                )
                self._emisores_anillo.pop(id_destino, None)
                try:
                    self._emisores_anillo[id_destino] = MessageMiddlewareQueueRabbitMQ(
                        self._config.host_mom, nombre_cola
                    )
                    self._emisores_anillo[id_destino].send(datos)
                except Exception as e2:
                    self._logger.error(
                        f"Retry fallido enviando a {nombre_cola}: {e2}",
                        exc_info=True,
                    )
