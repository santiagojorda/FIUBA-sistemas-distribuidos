from common.constantes_protocolo import (
    CABECERA,
    ESQUEMA,
    PAYLOAD,
    ID_CLIENTE,
    CANTIDAD,
    LOTES,
    COL_MONEDA_PAGO,
    COL_MARCA_TIEMPO,
    COL_MONTO_PAGADO,
)
from conversor_moneda import ConversorMoneda

class IndicesLote:
    def __init__(self, esquema: list):
        self.moneda_pago = esquema.index(COL_MONEDA_PAGO) if COL_MONEDA_PAGO in esquema else None
        self.marca_tiempo = esquema.index(COL_MARCA_TIEMPO) if COL_MARCA_TIEMPO in esquema else None
        self.monto_pagado = esquema.index(COL_MONTO_PAGADO) if COL_MONTO_PAGADO in esquema else None

class ProcesadorLotesConvertidor:
    def __init__(self, conversor: ConversorMoneda):
        self.conversor = conversor

    def procesar_payload(self, transaccion: dict, client_id: str) -> dict | None:
        lotes_filtrados = []
        for lote in transaccion.get(LOTES, []):
            cabecera = lote[CABECERA]
            esquema = cabecera[ESQUEMA]
            registros = lote[PAYLOAD]
            
            indices = IndicesLote(esquema)
            registros_filtrados = self._procesar_registros(registros, indices)
            
            if registros_filtrados:
                lotes_filtrados.append({
                    CABECERA: {
                        ESQUEMA: esquema,
                        ID_CLIENTE: cabecera.get(ID_CLIENTE, client_id),
                        CANTIDAD: len(registros_filtrados)
                    },
                    PAYLOAD: registros_filtrados
                })
                
        if not lotes_filtrados:
            return None

        return lotes_filtrados

    def _procesar_registros(self, registros, indices: IndicesLote):
        registros_filtrados = []
        for record_values in registros:
            try:
                curr_val = record_values[indices.moneda_pago] if indices.moneda_pago is not None else ""
                iso = self.conversor.obtener_iso(curr_val)
                if not iso:
                    continue
                
                ts_val = record_values[indices.marca_tiempo] if indices.marca_tiempo is not None else ""
                fecha = ts_val.split(" ")[0].replace("/", "-")
                
                amt_val = record_values[indices.monto_pagado] if indices.monto_pagado is not None else 0
                monto = float(amt_val)
                
                monto_usd = self.conversor.convertir_a_usd(monto, iso, fecha)
                if monto_usd is not None and monto_usd < 1.0:
                    registros_filtrados.append(record_values)
            except (ValueError, KeyError, IndexError):
                continue
        return registros_filtrados

    def coincide_limite(self, transaccion: dict) -> bool:
        iso = self.conversor.obtener_iso(transaccion.get(COL_MONEDA_PAGO, ""))
        if not iso:
            return False

        fecha = transaccion.get(COL_MARCA_TIEMPO, "").split(" ")[0].replace("/", "-")
        monto = float(transaccion.get(COL_MONTO_PAGADO, 0))
        monto_usd = self.conversor.convertir_a_usd(monto, iso, fecha)

        return monto_usd is not None and monto_usd < 1.0
