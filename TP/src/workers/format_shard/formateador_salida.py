from common.constantes_protocolo import ID_CLIENTE, LOTES, CABECERA, ESQUEMA, CANTIDAD, PAYLOAD
from constantes import ESQUEMA_SALIDA


def construir_resultado(id_cliente: str, registros: list) -> dict | None:
    if not registros:
        return None

    return {
        ID_CLIENTE: id_cliente,
        LOTES: [
            {
                CABECERA: {
                    ESQUEMA: ESQUEMA_SALIDA,
                    ID_CLIENTE: id_cliente,
                    CANTIDAD: len(registros),
                },
                PAYLOAD: registros,
            }
        ],
    }
