"""
Tests de persistencia para CounterWorker
=========================================
Cubren:
  - Caso 1: recovery del estado desde disco al reiniciarse
  - Caso 8: barrier_completada previene re-flush tras caída
  - Conteo correcto de batches y persistencia
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from common.persistencia import PersistidorEstado

BASE_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "q5_counter",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q5_in"]',
    "OUTPUT_QUEUES": '["q5_results"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
    "CRASH_AFTER_PERSIST": "false",
}


def _escribir_estado(tmp_path, client_id, estado):
    PersistidorEstado(f"counter_1_{client_id}", base_dir=str(tmp_path)).guardar(estado)


def _crear_worker(tmp_path, extra_env=None):
    import contador as mod
    env = {**BASE_ENV, **(extra_env or {})}
    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"), \
         patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)):
        w = mod.CounterWorker()
    return w


# ──────────────────────────────────────────────────────────────────
# Caso 1 — Recovery de estado desde disco
# ──────────────────────────────────────────────────────────────────

class TestCounterRecovery:

    def test_carga_count_desde_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 42})
        w = _crear_worker(tmp_path)
        assert w.estado._conteos["c1"] == 42

    def test_arranca_limpio_sin_estado_en_disco(self, tmp_path):
        w = _crear_worker(tmp_path)
        assert "c1" not in w.estado._conteos

    def test_multiples_clientes_se_recuperan_independientemente(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 10})
        _escribir_estado(tmp_path, "c2", {"count": 20})
        w = _crear_worker(tmp_path)
        assert w.estado._conteos["c1"] == 10
        assert w.estado._conteos["c2"] == 20

    def test_carpeta_con_estado_vacio_se_ignora(self, tmp_path):
        os.makedirs(tmp_path / "counter_1_c1", exist_ok=True)
        w = _crear_worker(tmp_path)
        assert "c1" not in w.estado._conteos


# ──────────────────────────────────────────────────────────────────
# Caso 8 — barrier_completada previene re-flush
# ──────────────────────────────────────────────────────────────────

class TestCounterBarrierCompletada:

    def test_estado_con_barrier_completada_no_se_carga_en_memoria(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 100, "barrera_completada": True})
        w = _crear_worker(tmp_path)
        assert "c1" not in w.estado._conteos

    def test_estado_con_barrier_completada_se_mantiene_en_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 100, "barrera_completada": True})
        _crear_worker(tmp_path)
        filepath = tmp_path / "counter_1_c1" / "estado.json"
        assert filepath.exists()

    def test_estado_sin_barrier_completada_si_se_carga(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 7, "barrera_completada": False})
        w = _crear_worker(tmp_path)
        assert w.estado._conteos["c1"] == 7


# ──────────────────────────────────────────────────────────────────
# Conteo correcto y persistencia
# ──────────────────────────────────────────────────────────────────

class TestCounterConteo:

    def test_incrementa_conteo_con_batches(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {"count": 5})
        w = _crear_worker(tmp_path)

        payload = {
            "client_id": "c1",
            "request_id": "req-nuevo",
            "batches": [{"header": {"schema": [], "client_id": "c1", "count": 3}, "payload": [[], [], []]}],
        }
        with patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)):
            w.procesar_payload("q5_in", "c1", payload, json.dumps(payload).encode(), MagicMock(), MagicMock())

        assert w.estado._conteos["c1"] == 8  # 5 + 3
        estado = PersistidorEstado("counter_1_c1", base_dir=str(tmp_path)).cargar()
        assert estado["count"] == 8

    def test_incrementa_conteo_sin_batches(self, tmp_path):
        w = _crear_worker(tmp_path)

        payload = {"client_id": "c1", "request_id": "req-1"}
        with patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)):
            w.procesar_payload("q5_in", "c1", payload, json.dumps(payload).encode(), MagicMock(), MagicMock())

        assert w.estado._conteos["c1"] == 1
