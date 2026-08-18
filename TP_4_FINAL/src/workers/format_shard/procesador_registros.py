import os
from common.message_protocol.internal import ParseadorMensajes
from constantes import (
    COL_FORMATO_PAGO, COL_MONTO_PAGADO, COL_BANCO_ORIGEN, COL_CUENTA,
    CLAVE_DATOS_TEMPRANO, CLAVE_PROMEDIOS, CLAVE_PROMEDIOS_LISTOS,
    CLAVE_CACHE_ESQUEMA, CLAVE_CACHE_REGISTROS,
    IDX_BANCO_ORIGEN, IDX_FORMATO_PAGO, IDX_MONTO_PAGADO, IDX_CUENTA,
    CLAVE_SUMA, CLAVE_CANTIDAD,
)


def _indice_columna(esquema: list, nombre: str):
    return esquema.index(nombre) if nombre in esquema else None


class ProcesadorRegistros:

    def acumular_temprano(self, estado: dict, esquema: list, registros: list):
        idx_formato = _indice_columna(esquema, COL_FORMATO_PAGO)
        idx_monto = _indice_columna(esquema, COL_MONTO_PAGADO)
        for valores_registro in registros:
            formato = valores_registro[idx_formato] if idx_formato is not None else ""
            monto = float(valores_registro[idx_monto] if idx_monto is not None else 0)
            if formato not in estado[CLAVE_DATOS_TEMPRANO]:
                estado[CLAVE_DATOS_TEMPRANO][formato] = {CLAVE_SUMA: 0, CLAVE_CANTIDAD: 0}
            estado[CLAVE_DATOS_TEMPRANO][formato][CLAVE_SUMA] += int(round(monto * 100))
            estado[CLAVE_DATOS_TEMPRANO][formato][CLAVE_CANTIDAD] += 1

    def acumular_temprano_individual(self, estado: dict, payload: dict):
        formato = payload.get(COL_FORMATO_PAGO, "")
        monto = float(payload.get(COL_MONTO_PAGADO, 0))
        if formato not in estado[CLAVE_DATOS_TEMPRANO]:
            estado[CLAVE_DATOS_TEMPRANO][formato] = {CLAVE_SUMA: 0, CLAVE_CANTIDAD: 0}
        estado[CLAVE_DATOS_TEMPRANO][formato][CLAVE_SUMA] += int(round(monto * 100))
        estado[CLAVE_DATOS_TEMPRANO][formato][CLAVE_CANTIDAD] += 1

    def calcular_promedios(self, estado: dict):
        for formato, stats in estado[CLAVE_DATOS_TEMPRANO].items():
            if stats[CLAVE_CANTIDAD] > 0:
                promedio_centavos = stats[CLAVE_SUMA] / stats[CLAVE_CANTIDAD]
                estado[CLAVE_PROMEDIOS][formato] = promedio_centavos / 100.0
        estado[CLAVE_PROMEDIOS_LISTOS] = True

    def filtrar_registros_tardios(self, estado: dict, ruta_cache: str) -> list:
        promedios = estado[CLAVE_PROMEDIOS]
        registros_filtrados = []

        if not os.path.exists(ruta_cache):
            return registros_filtrados

        indices_esquemas_cache = {}

        with open(ruta_cache, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    entry = ParseadorMensajes.deserializar(linea)
                except Exception:
                    continue

                esquema = entry[CLAVE_CACHE_ESQUEMA]
                registros_lote = entry[CLAVE_CACHE_REGISTROS]

                clave_esquema = tuple(esquema)
                if clave_esquema not in indices_esquemas_cache:
                    indices_esquemas_cache[clave_esquema] = {
                        IDX_BANCO_ORIGEN: _indice_columna(esquema, COL_BANCO_ORIGEN),
                        IDX_FORMATO_PAGO: _indice_columna(esquema, COL_FORMATO_PAGO),
                        IDX_MONTO_PAGADO: _indice_columna(esquema, COL_MONTO_PAGADO),
                        IDX_CUENTA: _indice_columna(esquema, COL_CUENTA),
                    }
                idx = indices_esquemas_cache[clave_esquema]

                for valores_registro in registros_lote:
                    formato = valores_registro[idx[IDX_FORMATO_PAGO]] if idx[IDX_FORMATO_PAGO] is not None else ""
                    monto = float(valores_registro[idx[IDX_MONTO_PAGADO]] if idx[IDX_MONTO_PAGADO] is not None else 0)
                    promedio = promedios.get(formato)

                    if promedio is None or monto >= promedio * 0.01:
                        continue

                    from_bank = valores_registro[idx[IDX_BANCO_ORIGEN]] if idx[IDX_BANCO_ORIGEN] is not None else ""
                    if isinstance(from_bank, str) and from_bank.isdigit():
                        from_bank = from_bank.lstrip("0") or "0"

                    account = valores_registro[idx[IDX_CUENTA]] if idx[IDX_CUENTA] is not None else ""
                    registros_filtrados.append([from_bank, account, formato, monto])

        return registros_filtrados

