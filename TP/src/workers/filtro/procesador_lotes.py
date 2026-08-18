from common.constantes_protocolo import CABECERA, ESQUEMA, PAYLOAD, ID_CLIENTE, CANTIDAD, LOTES, ID_SOLICITUD

class ProcesadorLotes:
    def __init__(self, regla_filtro):
        self.regla = regla_filtro

    def procesar_lote(self, lote: dict) -> dict | None:
        esquema = lote[CABECERA][ESQUEMA]
        registros = lote[PAYLOAD]
        
        filtrados = [
            reg for reg in registros
            if self.regla.coincide(dict(zip(esquema, reg)))
        ]
        
        if not filtrados:
            return None
            
        return {
            CABECERA: {
                ESQUEMA: esquema,
                ID_CLIENTE: lote[CABECERA].get(ID_CLIENTE),
                CANTIDAD: len(filtrados)
            },
            PAYLOAD: filtrados
        }

    def procesar_payload(self, payload: dict) -> dict | None:
        client_id = payload.get(ID_CLIENTE)
        lotes_filtrados = []
        
        for lote in payload.get(LOTES, []):
            filtrado = self.procesar_lote(lote)
            if filtrado:
                lotes_filtrados.append(filtrado)
                
        if not lotes_filtrados:
            return None

        resultado = {
            ID_CLIENTE: client_id,
            LOTES: lotes_filtrados
        }
        if ID_SOLICITUD in payload:
            resultado[ID_SOLICITUD] = payload[ID_SOLICITUD]
        return resultado
