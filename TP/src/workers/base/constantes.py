# Constantes de configuración de la base de los workers
from common.constantes_protocolo import CONF_PREFIJO_SHARD, CONF_TOTAL_WORKERS, CONF_CAMPO_HASH

CONF_PREFIJO_SHARD_ALT = "shard_prefix"
CONF_CAMPOS_HASH = "hash_fields"
CONF_CAMPO_CONDICION = "condition_field"
CONF_CASOS = "cases"
CONF_RUTEO = "routing"
CONF_INCLUIR_CLIENT_ID = "include_client_id"
CONF_VALOR = "value"
CONF_TIPO = "type"
CONF_CONDICIONAL = "conditional"

# Tipos de mensajes internos de coordinación
TIPO_MENSAJE = "type"
TIPO_EOF_RECIBIDO = "EOF_RECEIVED"
TIPO_WORKER_FINALIZADO = "WORKER_FINISHED"
TIPO_BARRERA_COMPLETA = "BARRIER_COMPLETE"
ORIGINADOR = "originator"
ID_WORKER = "worker_id"

# Claves de persistencia y estado común de los workers
CLAVE_BARRERA_COMPLETADA = "barrera_completada"
CLAVE_EOF_MENSAJE = "mensaje_eof"
CLAVE_EOF_MENSAJE_HEX = "mensaje_eof_hex"
CLAVE_IDS_PROCESADOS = "ids_procesados"
CLAVE_CACHE_REGISTROS = "records"
CLAVE_PROCESADOS = "procesados"
CLAVE_EMITIDOS = "emitidos"

# Claves de conteos locales en mensajes de coordinación entre workers
CLAVE_MENSAJES_PROCESADOS_LOCAL = "mensajes_procesados_local"
CLAVE_MENSAJES_EMITIDOS_LOCAL = "mensajes_emitidos_local"
CLAVE_TOTAL_MENSAJES_ENVIADOS = "total_mensajes_enviados"
