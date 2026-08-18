import uuid
from common import middleware, sharding
from common.message_protocol.internal import ParseadorMensajes
from common.constantes_protocolo import (
    ID_CLIENTE,
    ID_SOLICITUD,
    LOTES,
    CABECERA,
    ESQUEMA,
    PAYLOAD,
    CANTIDAD,
)
from base.constantes import (
    CONF_PREFIJO_SHARD,
    CONF_PREFIJO_SHARD_ALT,
    CONF_TOTAL_WORKERS,
    CONF_CAMPOS_HASH,
    CONF_CAMPO_HASH,
    CONF_CAMPO_CONDICION,
    CONF_CASOS,
    CONF_RUTEO,
    CONF_INCLUIR_CLIENT_ID,
    CONF_VALOR,
    CLAVE_TOTAL_MENSAJES_ENVIADOS,
)



def _normalizar_parte_hash(valor):
    if valor is None:
        return "N/A"
    texto = str(valor).strip()
    if not texto:
        return "N/A"
    if texto.isdigit():
        return texto.lstrip("0") or "0"
    return texto


class ColaSalidaDirecta:
    def __init__(self, host_mom, nombre_cola):
        self._cola = middleware.MessageMiddlewareQueueRabbitMQ(host_mom, nombre_cola)

    def enviar(self, mensaje, payload, es_eof, client_id, id_solicitud_origen):
        self._cola.send(mensaje)

    def cerrar(self):
        self._cola.close()


class ColaSalidaSharded:
    def __init__(self, host_mom, config_item):
        prefijo = config_item.get(CONF_PREFIJO_SHARD, config_item.get(CONF_PREFIJO_SHARD_ALT))
        self._total_workers = int(config_item.get(CONF_TOTAL_WORKERS) or 0)
        raw = config_item.get(CONF_CAMPOS_HASH) or (
            [config_item.get(CONF_CAMPO_HASH)] if config_item.get(CONF_CAMPO_HASH) else []
        )
        self._campos_hash = [campo for campo in raw if campo]
        self._colas = {
            id_worker: middleware.MessageMiddlewareQueueRabbitMQ(host_mom, f"{prefijo}_{id_worker}")
            for id_worker in range(1, self._total_workers + 1)
        }
        self._mensajes_enviados_por_shard = {}

    def enviar(self, mensaje, payload, es_eof, client_id, id_solicitud_origen):
        tiene_lotes = LOTES in payload and not es_eof
        if tiene_lotes:
            self._enviar_lotes(payload, client_id, id_solicitud_origen)
        elif es_eof:
            self._broadcast(mensaje, client_id)
        else:
            self._enviar_simple(mensaje, payload, client_id)

    def _broadcast(self, mensaje, client_id):
        payload = ParseadorMensajes.deserializar(mensaje)
        id_origen = payload.get(ID_SOLICITUD)
        for shard_id, cola in self._colas.items():
            total_shard = self._mensajes_enviados_por_shard.get(client_id, {}).get(shard_id, 0)
            payload[CLAVE_TOTAL_MENSAJES_ENVIADOS] = total_shard
            # El request_id del EOF debe ser único por (upstream, shard) y estable ante
            # redelivery. Si conservamos el id de origen del upstream (único por nodo),
            # la deduplicación downstream no descarta EOFs legítimos de distintos
            # upstreams que comparten el mismo contador local hacia este shard.
            if id_origen:
                payload[ID_SOLICITUD] = f"{id_origen}:{cola.queue_name}"
            else:
                payload[ID_SOLICITUD] = f"{client_id}:{cola.queue_name}:{total_shard + 1}"
            cola.send(ParseadorMensajes.serializar(payload))

    def _enviar_simple(self, mensaje, payload, client_id):
        valor_hash = self._valor_hash_desde_payload(payload)
        id_shard = sharding.obtener_id_shard(valor_hash, self._total_workers)
        if client_id:
            self._mensajes_enviados_por_shard.setdefault(client_id, {})
            self._mensajes_enviados_por_shard[client_id][id_shard] = (
                self._mensajes_enviados_por_shard[client_id].get(id_shard, 0) + 1
            )
        self._colas[id_shard].send(mensaje)

    def _enviar_lotes(self, payload, client_id, id_solicitud_origen):
        registros_por_shard = {}
        esquema_original = None

        for lote in payload[LOTES]:
            esquema_original = lote[CABECERA][ESQUEMA]
            for registro in lote[PAYLOAD]:
                valor_hash = self._valor_hash_desde_registro(esquema_original, registro)
                id_shard = sharding.obtener_id_shard(valor_hash, self._total_workers)
                if id_shard not in registros_por_shard:
                    registros_por_shard[id_shard] = []
                registros_por_shard[id_shard].append(registro)

        for id_shard, registros in registros_por_shard.items():
            id_derivado = (
                f"{id_solicitud_origen}:s{id_shard}"
                if id_solicitud_origen else str(uuid.uuid4())
            )
            payload_shard = {
                ID_CLIENTE: client_id,
                ID_SOLICITUD: id_derivado,
                LOTES: [{
                    CABECERA: {
                        ESQUEMA: esquema_original,
                        ID_CLIENTE: client_id,
                        CANTIDAD: len(registros),
                    },
                    PAYLOAD: registros,
                }],
            }
            if client_id:
                self._mensajes_enviados_por_shard.setdefault(client_id, {})
                self._mensajes_enviados_por_shard[client_id][id_shard] = (
                    self._mensajes_enviados_por_shard[client_id].get(id_shard, 0) + len(registros)
                )
            self._colas[id_shard].send(ParseadorMensajes.serializar(payload_shard))

    def _valor_hash_desde_registro(self, esquema, registro):
        partes = []
        for campo in self._campos_hash:
            if campo in esquema:
                indice = esquema.index(campo)
                partes.append(_normalizar_parte_hash(registro[indice]))
            else:
                partes.append("N/A")
        return "|".join(partes) if partes else "default"

    def _valor_hash_desde_payload(self, payload):
        partes = [
            _normalizar_parte_hash(payload.get(campo))
            for campo in self._campos_hash
        ]
        return "|".join(partes) if partes else "default"

    def cerrar(self):
        for cola in self._colas.values():
            cola.close()


class CasoCondicional:
    def __init__(self, host_mom, config_caso):
        ruteo = config_caso[CONF_RUTEO]
        prefijo = ruteo[CONF_PREFIJO_SHARD]
        self.valor = config_caso[CONF_VALOR]
        self.campo_hash = ruteo[CONF_CAMPO_HASH]
        self.total_workers = ruteo[CONF_TOTAL_WORKERS]
        self.incluir_client_id = ruteo.get(CONF_INCLUIR_CLIENT_ID, False)
        self.colas = {
            id_worker: middleware.MessageMiddlewareQueueRabbitMQ(host_mom, f"{prefijo}_{id_worker}")
            for id_worker in range(1, self.total_workers + 1)
        }

    def resolver_destino(self, valor_hash, client_id):
        if self.incluir_client_id:
            valor_hash = (
                f"{_normalizar_parte_hash(client_id)}"
                f"|{_normalizar_parte_hash(valor_hash)}"
            )
        id_shard = sharding.obtener_id_shard(valor_hash, self.total_workers)
        return self.colas[id_shard]

    def cerrar(self):
        for cola in self.colas.values():
            cola.close()


class ColaSalidaCondicional:
    def __init__(self, host_mom, config_item):
        self._campo_condicion = config_item[CONF_CAMPO_CONDICION]
        self._casos = [
            CasoCondicional(host_mom, caso)
            for caso in config_item[CONF_CASOS]
        ]
        self._mensajes_enviados_por_destino = {}

    def enviar(self, mensaje, payload, es_eof, client_id, id_solicitud_origen):
        tiene_lotes = LOTES in payload and not es_eof
        if tiene_lotes:
            self._enviar_lotes(payload, client_id, id_solicitud_origen)
        elif es_eof:
            self._broadcast(mensaje, client_id)
        else:
            self._enviar_simple(mensaje, payload, client_id)

    def _broadcast(self, mensaje, client_id):
        payload = ParseadorMensajes.deserializar(mensaje)
        id_origen = payload.get(ID_SOLICITUD)
        for caso in self._casos:
            for shard_id, cola in caso.colas.items():
                total_cola = self._mensajes_enviados_por_destino.get(client_id, {}).get(cola.queue_name, 0)
                payload[CLAVE_TOTAL_MENSAJES_ENVIADOS] = total_cola
                # Mismo criterio que ColaSalidaSharded: request_id de EOF único por
                # (upstream, destino) y estable ante redelivery.
                if id_origen:
                    payload[ID_SOLICITUD] = f"{id_origen}:{cola.queue_name}"
                else:
                    payload[ID_SOLICITUD] = f"{client_id}:{cola.queue_name}:{total_cola + 1}"
                cola.send(ParseadorMensajes.serializar(payload))

    def _enviar_simple(self, mensaje, payload, client_id):
        valor_campo = str(payload.get(self._campo_condicion, ""))[:10]
        for caso in self._casos:
            if not self._evaluar_between(valor_campo, caso.valor):
                continue
            valor_hash = payload.get(caso.campo_hash, "default")
            cola = caso.resolver_destino(valor_hash, client_id)
            if client_id:
                self._mensajes_enviados_por_destino.setdefault(client_id, {})
                self._mensajes_enviados_por_destino[client_id][cola.queue_name] = (
                    self._mensajes_enviados_por_destino[client_id].get(cola.queue_name, 0) + 1
                )
            cola.send(mensaje)
            break

    def _enviar_lotes(self, payload, client_id, id_solicitud_origen):
        registros_por_cola = {}

        for lote in payload[LOTES]:
            esquema = lote[CABECERA][ESQUEMA]
            idx_condicion = (
                esquema.index(self._campo_condicion)
                if self._campo_condicion in esquema else None
            )

            for registro in lote[PAYLOAD]:
                valor_campo = (
                    str(registro[idx_condicion])[:10]
                    if idx_condicion is not None else ""
                )
                cola_destino = self._resolver_destino_registro(
                    valor_campo, esquema, registro, client_id
                )
                if cola_destino is None:
                    continue
                if cola_destino not in registros_por_cola:
                    registros_por_cola[cola_destino] = (esquema, [])
                registros_por_cola[cola_destino][1].append(registro)

        for indice, (cola_destino, (esquema, registros)) in enumerate(registros_por_cola.items()):
            id_derivado = (
                f"{id_solicitud_origen}:c{indice}"
                if id_solicitud_origen else str(uuid.uuid4())
            )
            payload_cola = {
                ID_CLIENTE: client_id,
                ID_SOLICITUD: id_derivado,
                LOTES: [{
                    CABECERA: {
                        ESQUEMA: esquema,
                        ID_CLIENTE: client_id,
                        CANTIDAD: len(registros),
                    },
                    PAYLOAD: registros,
                }],
            }
            if client_id:
                self._mensajes_enviados_por_destino.setdefault(client_id, {})
                self._mensajes_enviados_por_destino[client_id][cola_destino.queue_name] = (
                    self._mensajes_enviados_por_destino[client_id].get(cola_destino.queue_name, 0) + len(registros)
                )
            cola_destino.send(ParseadorMensajes.serializar(payload_cola))

    def _resolver_destino_registro(self, valor_campo, esquema, registro, client_id):
        for caso in self._casos:
            if not self._evaluar_between(valor_campo, caso.valor):
                continue
            indice_hash = esquema.index(caso.campo_hash) if caso.campo_hash in esquema else None
            valor_hash = registro[indice_hash] if indice_hash is not None else "default"
            return caso.resolver_destino(valor_hash, client_id)
        return None

    def _evaluar_between(self, valor, rango):
        limites = [limite.strip() for limite in rango.split(",")]
        return limites[0] <= valor <= limites[1]

    def cerrar(self):
        for caso in self._casos:
            caso.cerrar()
