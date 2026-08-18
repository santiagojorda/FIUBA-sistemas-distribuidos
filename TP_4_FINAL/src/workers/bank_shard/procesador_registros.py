from common.sharding import normalizar_valor_hash
from constantes import (
    COL_BANCO_ORIGEN, COL_CUENTA, COL_ID_BANCO, COL_NOMBRE_BANCO,
    COL_MONTO_RECIBIDO, NOMBRE_BANCO_DESCONOCIDO,
    CLAVE_NOMBRE_BANCO, CLAVE_MONTO_MAXIMO, CLAVE_CUENTAS,
)
from common.constantes_protocolo import COL_MONTO_PAGADO


def _normalizar_id_banco(valor) -> str:
    s = normalizar_valor_hash(valor)
    if s != "N/A" and s.isdigit():
        return s.lstrip("0") or "0"
    return s


def _obtener_o_crear_banco(estado: dict, id_banco: str) -> dict:
    if id_banco not in estado:
        estado[id_banco] = {
            CLAVE_NOMBRE_BANCO: NOMBRE_BANCO_DESCONOCIDO,
            CLAVE_MONTO_MAXIMO: 0.0,
            CLAVE_CUENTAS: [],
        }
    return estado[id_banco]


def _indice_columna(esquema: list, nombre: str):
    return esquema.index(nombre) if nombre in esquema else None


def _actualizar_monto_maximo(datos_banco: dict, monto: float, cuenta: str | None):
    if monto > datos_banco[CLAVE_MONTO_MAXIMO]:
        datos_banco[CLAVE_MONTO_MAXIMO] = monto
        datos_banco[CLAVE_CUENTAS] = [cuenta] if cuenta else []
    elif monto == datos_banco[CLAVE_MONTO_MAXIMO] and monto > 0 and cuenta:
        if cuenta not in datos_banco[CLAVE_CUENTAS]:
            datos_banco[CLAVE_CUENTAS].append(cuenta)


class ProcesadorRegistros:

    def procesar_transacciones(self, estado: dict, esquema: list, registros: list):
        idx_banco = _indice_columna(esquema, COL_BANCO_ORIGEN)
        idx_monto_pagado = _indice_columna(esquema, COL_MONTO_PAGADO)
        idx_monto_recibido = _indice_columna(esquema, COL_MONTO_RECIBIDO)
        idx_cuenta = _indice_columna(esquema, COL_CUENTA)

        for registro in registros:
            id_banco = _normalizar_id_banco(registro[idx_banco] if idx_banco is not None else None)
            if not id_banco:
                continue

            datos_banco = _obtener_o_crear_banco(estado, id_banco)

            monto_str = "0"
            if idx_monto_pagado is not None:
                monto_str = registro[idx_monto_pagado]
            elif idx_monto_recibido is not None:
                monto_str = registro[idx_monto_recibido]

            cuenta = registro[idx_cuenta] if idx_cuenta is not None else None
            _actualizar_monto_maximo(datos_banco, float(monto_str), cuenta)

    def procesar_bancos(self, estado: dict, esquema: list, registros: list):
        idx_id = _indice_columna(esquema, COL_ID_BANCO)
        idx_nombre = _indice_columna(esquema, COL_NOMBRE_BANCO)

        for registro in registros:
            id_banco = _normalizar_id_banco(registro[idx_id] if idx_id is not None else None)
            if not id_banco:
                continue

            datos_banco = _obtener_o_crear_banco(estado, id_banco)
            if idx_nombre is not None:
                datos_banco[CLAVE_NOMBRE_BANCO] = registro[idx_nombre]

    def procesar_transaccion_individual(self, estado: dict, payload: dict):
        id_banco = _normalizar_id_banco(payload.get(COL_BANCO_ORIGEN))
        if not id_banco:
            return
        datos_banco = _obtener_o_crear_banco(estado, id_banco)
        monto_str = payload.get(COL_MONTO_PAGADO, payload.get(COL_MONTO_RECIBIDO, "0"))
        cuenta = payload.get(COL_CUENTA, "")
        _actualizar_monto_maximo(datos_banco, float(monto_str), cuenta)

    def procesar_banco_individual(self, estado: dict, payload: dict):
        id_banco = _normalizar_id_banco(payload.get(COL_ID_BANCO))
        if not id_banco:
            return
        datos_banco = _obtener_o_crear_banco(estado, id_banco)
        datos_banco[CLAVE_NOMBRE_BANCO] = payload.get(COL_NOMBRE_BANCO, NOMBRE_BANCO_DESCONOCIDO)
