from common.logger import obtener_logger
from common.constantes_protocolo import ID_CLIENTE, LOTES, CABECERA, ESQUEMA, CANTIDAD, PAYLOAD
from constantes import (
    ESQUEMA_SALIDA, NOMBRE_BANCO_DESCONOCIDO,
    CLAVE_NOMBRE_BANCO, CLAVE_MONTO_MAXIMO, CLAVE_CUENTAS,
)

logger = obtener_logger(__name__)


def construir_resultado(client_id: str, datos_bancos: dict) -> dict | None:
    registros = []

    for id_banco, datos_banco in datos_bancos.items():
        if datos_banco[CLAVE_MONTO_MAXIMO] <= 0.0:
            continue
        if datos_banco[CLAVE_NOMBRE_BANCO] == NOMBRE_BANCO_DESCONOCIDO:
            logger.warning(f"Descartando banco {id_banco} para {client_id}: nombre desconocido.")
            continue

        cuentas = datos_banco.get(CLAVE_CUENTAS) or [datos_banco.get("account", "")]
        for cuenta in cuentas:
            registros.append([
                id_banco,
                cuenta,
                datos_banco[CLAVE_NOMBRE_BANCO],
                datos_banco[CLAVE_MONTO_MAXIMO],
            ])

    if not registros:
        return None

    return {
        ID_CLIENTE: client_id,
        LOTES: [
            {
                CABECERA: {
                    ESQUEMA: ESQUEMA_SALIDA,
                    ID_CLIENTE: client_id,
                    CANTIDAD: len(registros),
                },
                PAYLOAD: registros,
            }
        ],
    }
