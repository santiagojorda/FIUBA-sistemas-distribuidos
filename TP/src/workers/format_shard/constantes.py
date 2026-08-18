from common.constantes_protocolo import (
    COL_MONTO_PAGADO, COL_BANCO_ORIGEN, COL_CUENTA,
    ID_SOLICITUD as CLAVE_CACHE_SOLICITUD,
    ESQUEMA as CLAVE_CACHE_ESQUEMA,
    CANTIDAD as CLAVE_CANTIDAD,
)
from base.constantes import (
    CLAVE_CACHE_REGISTROS,
    CLAVE_BARRERA_COMPLETADA,
    CLAVE_EOF_MENSAJE,
    CLAVE_EOF_MENSAJE_HEX,
    CLAVE_IDS_PROCESADOS
)

PREFIJO_FORMATEADOR_SHARD = "format_shard"

# Columnas y esquemas
COL_FORMATO_PAGO = "Payment Format"

ESQUEMA_SALIDA = [COL_BANCO_ORIGEN, COL_CUENTA, COL_FORMATO_PAGO, COL_MONTO_PAGADO]

# Claves del estado en memoria
CLAVE_TEMPRANO_CERRADO = "temprano_cerrado"
CLAVE_TARDIO_CERRADO = "tardio_cerrado"
CLAVE_PROMEDIOS_LISTOS = "promedios_listos"
CLAVE_PROMEDIOS = "promedios"
CLAVE_DATOS_TEMPRANO = "datos_temprano"
CLAVE_CACHE_PROCESADO = "cache_procesado"

# Colas upstream
COLA_TEMPRANO = "temprano"
COLA_TARDIO = "tardio"

# Identificadores de columnas para índices
IDX_BANCO_ORIGEN = "from_bank"
IDX_FORMATO_PAGO = "formato"
IDX_MONTO_PAGADO = "monto"
IDX_CUENTA = "account"

# Claves de acumuladores internos
CLAVE_SUMA = "suma"


