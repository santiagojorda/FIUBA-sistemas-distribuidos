import json

from config_contador import ConfigContador
from operadores_contador import OP_MAYOR_QUE, OP_MAYOR_IGUAL
from common.constantes_protocolo import ID_CLIENTE, LOTES, CABECERA, ESQUEMA, CANTIDAD, PAYLOAD
from common.persistencia import TAMANIO_BATCH_EMISION

MODO_EXPLODE = "explode"


class EmisorResultados:
    """
    Recorre los grupos acumulados, filtra por la condición configurada
    y envía los resultados en lotes hacia la cola de salida.

    Modos de emisión:
      explode    → un registro por cada ítem del set de valores distintos.
                   Incluye campos de grupo y de valor.
      aggregate  → un registro por grupo con el conteo en COUNT_OUTPUT_FIELD.
    """

    def __init__(self, config: ConfigContador, enviar_fn):
        self._config = config
        self._enviar = enviar_fn

    def emitir(self, client_id: str, grupos: dict) -> int:
        """
        Filtra y envía resultados para todos los grupos de un cliente.
        Retorna la cantidad de registros emitidos.
        """
        esquema = self._construir_esquema()
        batch: list = []
        enviados = 0

        for clave_grupo, conjunto_valores in grupos.items():
            if not self._cumple_condicion(len(conjunto_valores)):
                continue

            if self._config.modo_emision == MODO_EXPLODE:
                for clave_valor in conjunto_valores:
                    batch.append(list(clave_grupo) + list(clave_valor))
            else:
                batch.append(list(clave_grupo) + [len(conjunto_valores)])

            if len(batch) >= TAMANIO_BATCH_EMISION:
                self._enviar_batch(client_id, esquema, batch)
                enviados += len(batch)
                batch = []

        if batch:
            self._enviar_batch(client_id, esquema, batch)
            enviados += len(batch)

        return enviados

    def _construir_esquema(self) -> list[str]:
        if self._config.modo_emision == MODO_EXPLODE:
            return self._config.campos_salida_grupo + self._config.campos_salida_valor
        return self._config.campos_salida_grupo + [self._config.campo_conteo]

    def _cumple_condicion(self, tamanio: int) -> bool:
        esperado = self._config.conteo_esperado
        op = self._config.operador
        if op == OP_MAYOR_QUE:
            return tamanio > esperado
        if op == OP_MAYOR_IGUAL:
            return tamanio >= esperado
        return tamanio == esperado  # OP_IGUAL por defecto

    def _enviar_batch(self, client_id: str, esquema: list[str], registros: list):
        payload = {
            ID_CLIENTE: client_id,
            LOTES: [{
                CABECERA: {
                    ESQUEMA: esquema,
                    ID_CLIENTE: client_id,
                    CANTIDAD: len(registros),
                },
                PAYLOAD: registros,
            }],
        }
        self._enviar(json.dumps(payload).encode("utf-8"), payload=payload)
