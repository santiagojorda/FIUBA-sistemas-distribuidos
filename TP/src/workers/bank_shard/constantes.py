from common.constantes_protocolo import COL_BANCO_ORIGEN, COL_CUENTA, COL_MONTO_PAGADO
from base.constantes import (
    CLAVE_BARRERA_COMPLETADA, CLAVE_EOF_MENSAJE,
    CLAVE_EOF_MENSAJE_HEX, CLAVE_IDS_PROCESADOS
)

PREFIJO_BANK_SHARD = "bank_shard"

# Columnas específicas del bank_shard
COL_ID_BANCO = "Bank ID"
COL_NOMBRE_BANCO = "Bank Name"
COL_MONTO_RECIBIDO = "Amount Received"

# Esquema de salida
ESQUEMA_SALIDA = [COL_BANCO_ORIGEN, COL_CUENTA, COL_NOMBRE_BANCO, COL_MONTO_PAGADO]

# Valores por defecto
NOMBRE_BANCO_DESCONOCIDO = "Desconocido"

# Claves del estado de banco en memoria
CLAVE_NOMBRE_BANCO = "bank_name"
CLAVE_MONTO_MAXIMO = "max_amount"
CLAVE_CUENTAS = "accounts"

# Claves de persistencia
CLAVE_TX_EOF_COUNT = "tx_eof_count"
CLAVE_BANK_EOF_COUNT = "bank_eof_count"
CLAVE_FLUSH_INICIADO = "flush_iniciado"
CLAVE_BANCOS = "bancos"

# Identificadores de cola upstream
COLA_TRANSACCIONES = "transactions"
COLA_BANCOS = "banks"

# Variables de entorno
ENV_TOTAL_TX_UPSTREAM = "TOTAL_TX_UPSTREAM"
ENV_TOTAL_BANK_UPSTREAM = "TOTAL_BANK_UPSTREAM"
# Persistencia por lotes
INTERVALO_PERSISTENCIA = 500

