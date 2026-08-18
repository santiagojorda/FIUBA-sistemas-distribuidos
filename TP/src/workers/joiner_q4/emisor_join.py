import json

from common.constantes_protocolo import ID_CLIENTE, LOTES, CABECERA, ESQUEMA, CANTIDAD, PAYLOAD
from common.persistencia import TAMANIO_BATCH_EMISION
from common.logger import obtener_logger

logger = obtener_logger(__name__)

_ESQUEMA_SALIDA = ["a_bank", "a_account", "b_bank", "b_account", "c_bank", "c_account"]


class EmisorResultados:
    """
    Realiza el join entre aristas scatter (A→B) y transacciones (B→C),
    filtra caminos degenerados y envía los resultados en lotes.

    Filtro "celes": descarta tripletas donde A==B, B==C o A==C,
    ya que representan lazos en el grafo que no son caminos válidos.
    """

    def __init__(self, enviar_fn):
        self._enviar = enviar_fn

    def emitir(self, client_id: str, scatter: dict, txns: dict) -> int:
        """
        Genera tripletas (A, B, C) para todos los b_key que aparecen en
        ambos índices. Retorna la cantidad de registros emitidos.
        """
        matches = [k for k in scatter if k in txns]
        logger.info(f"[EmisorResultados] scatter_keys={len(scatter)} txns_keys={len(txns)} matches={len(matches)}")
        if matches:
            logger.info(f"[EmisorResultados] match sample: {matches[:3]}")

        batch: list = []
        enviados = 0

        for b_key, lista_a in scatter.items():
            if b_key not in txns:
                continue
            b_bank, b_account = b_key.split("|", 1)

            for c_bank, c_account in txns[b_key]:
                for a_bank, a_account in lista_a:
                    if self._es_degenerado(a_bank, a_account, b_bank, b_account, c_bank, c_account):
                        continue
                    batch.append([a_bank, a_account, b_bank, b_account, c_bank, c_account])

                    if len(batch) >= TAMANIO_BATCH_EMISION:
                        self._enviar_batch(client_id, batch)
                        enviados += len(batch)
                        batch = []

        if batch:
            self._enviar_batch(client_id, batch)
            enviados += len(batch)

        return enviados

    def _es_degenerado(self, a_bank, a_account, b_bank, b_account, c_bank, c_account) -> bool:
        """Retorna True si el camino A→B→C tiene un lazo (A=B, B=C o A=C)."""
        return (
            (a_bank, a_account) == (b_bank, b_account)
            or (b_bank, b_account) == (c_bank, c_account)
            or (a_bank, a_account) == (c_bank, c_account)
        )

    def _enviar_batch(self, client_id: str, registros: list):
        payload = {
            ID_CLIENTE: client_id,
            LOTES: [{
                CABECERA: {
                    ESQUEMA: _ESQUEMA_SALIDA,
                    ID_CLIENTE: client_id,
                    CANTIDAD: len(registros),
                },
                PAYLOAD: registros,
            }],
        }
        self._enviar(json.dumps(payload).encode("utf-8"), payload=payload)
