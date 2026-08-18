"""
Tests de persistencia para ContadorDistintoWorker
======================================================
Cubren:
  - Caso 1: recovery de grupos y vistos desde disco al reiniciarse
  - Caso 4: dedup propio (_vistos) en ventana crash-antes-de-ack
  - Caso 8: barrier_completada previene re-flush tras caída en al_completar_cliente
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from common.persistencia import PersistidorEstado
from base.constantes import CLAVE_BARRERA_COMPLETADA, CLAVE_IDS_PROCESADOS


BASE_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "q4_sumador",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q4_to_sumador_1"]',
    "OUTPUT_QUEUES": '["q4_scatter_edges_1"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
    "GROUP_FIELDS": "From Bank,Account",
    "GROUP_OUTPUT_FIELDS": "from_bank,from_account",
    "VALUE_FIELDS": "To Bank,Account.1",
    "VALUE_OUTPUT_FIELDS": "to_bank,to_account",
    "EXPECTED_COUNT": "5",
    "COMPARISON_OPERATOR": "gt",
    "EMIT_MODE": "explode",
}

# node_prefix=q4_sumador, node_id=1 → nombre = "gdc_q4_sumador_1_{client_id}"
def _nombre_nodo(client_id):
    return f"gdc_q4_sumador_1_{client_id}"


def _escribir_estado(tmp_path, client_id, estado):
    PersistidorEstado(_nombre_nodo(client_id), base_dir=str(tmp_path)).guardar(estado)


def _crear_worker(tmp_path, extra_env=None):
    import workers.contador_distinto.contador_distinto as mod
    env = {**BASE_ENV, **(extra_env or {})}
    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"), \
         patch.object(mod, "BASE_DIR", str(tmp_path)):
        w = mod.ContadorDistintoWorker()
    return w


def _grupos_serializados(grupos_dict):
    """Serializa {tuple: set_of_tuples} al formato del JSON de estado."""
    return {
        json.dumps(list(gkey)): [list(vkey) for vkey in vset]
        for gkey, vset in grupos_dict.items()
    }


# ──────────────────────────────────────────────────────────────────
# Caso 1 — Recovery de estado desde disco
# ──────────────────────────────────────────────────────────────────

class TestGDCRecovery:

    def test_carga_grupos_y_vistos_desde_disco(self, tmp_path):
        grupos = {("bank1", "acc1"): {("bank2", "acc2"), ("bank3", "acc3")}}
        _escribir_estado(tmp_path, "c1", {
            "grupos": _grupos_serializados(grupos),
            CLAVE_IDS_PROCESADOS: ["r1"],
        })
        w = _crear_worker(tmp_path)
        assert ("bank1", "acc1") in w.acumulador._grupos["c1"]
        assert ("bank2", "acc2") in w.acumulador._grupos["c1"][("bank1", "acc1")]
        assert w.acumulador._vistos["c1"] == {"r1"}

    def test_arranca_limpio_sin_estado_en_disco(self, tmp_path):
        w = _crear_worker(tmp_path)
        assert "c1" not in w.acumulador._grupos

    def test_multiples_clientes_se_recuperan_independientemente(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"grupos": _grupos_serializados({("b1", "a1"): {("b2", "a2")}}), CLAVE_IDS_PROCESADOS: []})
        _escribir_estado(tmp_path, "c2", {"grupos": _grupos_serializados({("b3", "a3"): {("b4", "a4")}}), CLAVE_IDS_PROCESADOS: ["x"]})
        w = _crear_worker(tmp_path)
        assert ("b1", "a1") in w.acumulador._grupos["c1"]
        assert ("b3", "a3") in w.acumulador._grupos["c2"]
        assert w.acumulador._vistos["c2"] == {"x"}


# ──────────────────────────────────────────────────────────────────
# Caso 8 — barrier_completada previene re-flush
# ──────────────────────────────────────────────────────────────────

class TestGDCBarrierCompletada:
 
    def test_estado_con_barrier_completada_no_se_carga_en_memoria(self, tmp_path):
        grupos = {("bank1", "acc1"): {("bank2", "acc2")}}
        _escribir_estado(tmp_path, "c1", {
            "grupos": _grupos_serializados(grupos),
            CLAVE_IDS_PROCESADOS: ["r1"],
            CLAVE_BARRERA_COMPLETADA: True,
        })
        w = _crear_worker(tmp_path)
        assert "c1" not in w.acumulador._grupos
        assert "c1" not in w.acumulador._vistos
 
    def test_estado_con_barrier_completada_se_mantiene_en_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"grupos": {}, CLAVE_IDS_PROCESADOS: [], CLAVE_BARRERA_COMPLETADA: True})
        _crear_worker(tmp_path)
        filepath = tmp_path / _nombre_nodo("c1") / "estado.json"
        assert filepath.exists()
 
    def test_estado_sin_barrier_completada_si_se_carga(self, tmp_path):
        grupos = {("b1", "a1"): {("b2", "a2")}}
        _escribir_estado(tmp_path, "c1", {
            "grupos": _grupos_serializados(grupos),
            CLAVE_IDS_PROCESADOS: [],
            CLAVE_BARRERA_COMPLETADA: False,
        })
        w = _crear_worker(tmp_path)
        assert "c1" in w.acumulador._grupos


# ──────────────────────────────────────────────────────────────────
# Caso 4 — _vistos evita doble acumulación en ventana crash-antes-de-ack
# ──────────────────────────────────────────────────────────────────

class TestGDCDedupPropio:

    def test_request_id_duplicado_no_agrega_al_grupo(self, tmp_path):
        grupos = {("bank1", "acc1"): {("bank2", "acc2")}}
        _escribir_estado(tmp_path, "c1", {
            "grupos": _grupos_serializados(grupos),
            CLAVE_IDS_PROCESADOS: ["req-dup"],
        })
        w = _crear_worker(tmp_path)

        ack = MagicMock()
        nack = MagicMock()
        payload = {
            "client_id": "c1",
            "request_id": "req-dup",
            "batches": [{
                "header": {"schema": ["From Bank", "Account", "To Bank", "Account.1"], "client_id": "c1", "count": 1},
                "payload": [["bank1", "acc1", "bank3", "acc3"]],
            }],
        }
        import workers.contador_distinto.contador_distinto as mod
        with patch.object(mod, "BASE_DIR", str(tmp_path)):
            w.procesar_payload("q4_to_sumador_1", "c1", payload, json.dumps(payload).encode(), ack, nack)

        # el grupo sigue con solo 1 valor (no se agregó bank3/acc3)
        assert len(w.acumulador._grupos["c1"][("bank1", "acc1")]) == 1
        ack.assert_called_once()
        nack.assert_not_called()

    def test_request_id_nuevo_agrega_al_grupo_y_persiste(self, tmp_path):
        grupos = {("bank1", "acc1"): {("bank2", "acc2")}}
        _escribir_estado(tmp_path, "c1", {
            "grupos": _grupos_serializados(grupos),
            CLAVE_IDS_PROCESADOS: ["req-viejo"],
        })
        w = _crear_worker(tmp_path)

        payload = {
            "client_id": "c1",
            "request_id": "req-nuevo",
            "batches": [{
                "header": {"schema": ["From Bank", "Account", "To Bank", "Account.1"], "client_id": "c1", "count": 1},
                "payload": [["bank1", "acc1", "bank3", "acc3"]],
            }],
        }
        import workers.contador_distinto.contador_distinto as mod
        with patch.object(mod, "BASE_DIR", str(tmp_path)):
            w.procesar_payload("q4_to_sumador_1", "c1", payload, json.dumps(payload).encode(), MagicMock(), MagicMock())

        assert ("bank3", "acc3") in w.acumulador._grupos["c1"][("bank1", "acc1")]
        assert "req-nuevo" in w.acumulador._vistos["c1"]
