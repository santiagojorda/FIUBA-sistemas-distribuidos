from common.constantes_protocolo import (
    CABECERA, ESQUEMA, PAYLOAD, LOTES,
    ID_CLIENTE, CANTIDAD, ID_SOLICITUD,
)


class ProcesadorLotes:
    """
    Proyecta registros conservando solo los campos configurados.

    Soporta dos formatos de entrada:
      - Lotes (columnar): un payload con múltiples batches en formato esquema+registros.
      - Individual:       un dict plano con los campos del registro.

    Opcionalmente convierte a entero los campos listados en campos_enteros.
    """

    def __init__(self, campos: list[str], campos_enteros: set[str]):
        self._campos = campos
        self._campos_enteros = campos_enteros

    def procesar_payload(self, payload: dict, client_id: str) -> dict | None:
        """Proyecta todos los lotes del payload. Retorna None si no queda ninguno."""
        lotes_proyectados = []
        for lote in payload.get(LOTES, []):
            proyectado = self._procesar_lote(lote, client_id)
            if proyectado:
                lotes_proyectados.append(proyectado)

        if not lotes_proyectados:
            return None

        resultado = {ID_CLIENTE: client_id, LOTES: lotes_proyectados}
        if ID_SOLICITUD in payload:
            resultado[ID_SOLICITUD] = payload[ID_SOLICITUD]
        return resultado

    def procesar_individual(self, transaccion: dict, client_id: str) -> dict:
        """Proyecta un registro suelto en formato dict."""
        proyectado = {ID_CLIENTE: transaccion.get(ID_CLIENTE, client_id)}
        for campo in self._campos:
            if campo in transaccion:
                proyectado[campo] = self._convertir_valor(campo, transaccion[campo])
        return proyectado

    def _procesar_lote(self, lote: dict, client_id: str) -> dict | None:
        esquema = lote[CABECERA][ESQUEMA]
        registros = lote[PAYLOAD]

        nuevo_esquema = [col for col in self._campos if col in esquema]
        indices_columna = {col: i for i, col in enumerate(esquema)}

        registros_proyectados = [
            [self._convertir_valor(col, valores[indices_columna[col]]) for col in nuevo_esquema]
            for valores in registros
        ]

        if not registros_proyectados:
            return None

        return {
            CABECERA: {
                ESQUEMA: nuevo_esquema,
                ID_CLIENTE: lote[CABECERA].get(ID_CLIENTE, client_id),
                CANTIDAD: len(registros_proyectados),
            },
            PAYLOAD: registros_proyectados,
        }

    def _convertir_valor(self, campo: str, valor):
        """Convierte el valor a entero si el campo está en campos_enteros."""
        if campo in self._campos_enteros:
            try:
                return int(valor)
            except (ValueError, TypeError):
                pass
        return valor
