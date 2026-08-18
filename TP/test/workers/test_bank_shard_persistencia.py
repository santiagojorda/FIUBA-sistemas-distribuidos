"""
Tests de persistencia para AgregadorBancarioWorker (bank_shard)
===============================================================
Cubren:
  - Caso 1: recovery del estado desde disco al reiniciarse
  - Caso 4: dedup propio (_ids_procesados) en ventana crash-entre-persist-y-ack
  - Caso 7: recovery con ambas colas cerradas dispara barrera diferida
  - Caso 8: barrier_completada previene re-flush tras caída
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from common.persistencia import PersistidorEstado

from constantes import (
    CLAVE_TX_EOF_COUNT, CLAVE_BANK_EOF_COUNT, CLAVE_EOF_MENSAJE,
    CLAVE_FLUSH_INICIADO, CLAVE_BARRERA_COMPLETADA,
)


BASE_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "q2_agregador_shard",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q2_transactions_1", "q2_banks_1"]',
    "OUTPUT_QUEUES": '["q2_results"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
    "CRASH_PRE_BARRERA": "false",
}

NODE_PREFIX = "bank_shard_1"


def _escribir_estado(tmp_path, client_id, estado):
    PersistidorEstado(f"{NODE_PREFIX}_{client_id}", base_dir=str(tmp_path)).guardar(estado)


def _crear_worker(tmp_path, extra_env=None):
    import agregador_bancario as mod
    import config_agregador
    env = {**BASE_ENV, **(extra_env or {})}

    original_init = config_agregador.ConfigAgregador.__init__

    def patched_init(self, nid):
        self.base_dir = str(tmp_path)
        self.prefijo_nodo = NODE_PREFIX
        self.total_tx_upstream = 1
        self.total_bank_upstream = 1

    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"), \
         patch.object(config_agregador.ConfigAgregador, "__init__", patched_init):
        w = mod.AgregadorBancarioWorker()
    return w


# ──────────────────────────────────────────────────────────────────
# Caso 1 — Recovery de estado desde disco
# ──────────────────────────────────────────────────────────────────

class TestBankShardRecovery:

    def test_carga_bancos_y_request_ids_desde_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"bank1": {"bank_name": "Test", "max_amount": 100.0}},
            "ids_procesados": ["r1", "r2"],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert "c1" in w._datos_bancos
        assert w._datos_bancos["c1"]["bank1"]["bank_name"] == "Test"
        assert w._ids_procesados["c1"] == {"r1", "r2"}

    def test_arranca_limpio_sin_estado_en_disco(self, tmp_path):
        w = _crear_worker(tmp_path)
        assert "c1" not in w._datos_bancos
        assert "c1" not in w._ids_procesados

    def test_multiples_clientes_se_recuperan_independientemente(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "A", "max_amount": 10.0}},
            "ids_procesados": [],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        _escribir_estado(tmp_path, "c2", {
            "bancos": {"b2": {"bank_name": "B", "max_amount": 20.0}},
            "ids_procesados": ["x"],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert w._datos_bancos["c1"]["b1"]["bank_name"] == "A"
        assert w._datos_bancos["c2"]["b2"]["bank_name"] == "B"
        assert w._ids_procesados["c2"] == {"x"}

    def test_eof_state_se_recupera_correctamente(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 0,
            "mensaje_eof_hex": b"eof_msg".hex(),
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert w._estado_eof["c1"][CLAVE_TX_EOF_COUNT] == 1
        assert w._estado_eof["c1"][CLAVE_BANK_EOF_COUNT] == 0
        assert w._estado_eof["c1"][CLAVE_EOF_MENSAJE] == b"eof_msg"


# ──────────────────────────────────────────────────────────────────
# Caso 8 — barrera_completada previene re-flush
# ──────────────────────────────────────────────────────────────────

class TestBankShardBarrierCompletada:

    def test_estado_con_barrier_completada_no_se_carga_en_memoria(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "X", "max_amount": 5.0}},
            "ids_procesados": ["r1"],
            "tx_eof_count": 1,
            "bank_eof_count": 1,
            "mensaje_eof_hex": None,
            "flush_iniciado": True,
            "barrera_completada": True,
        })
        w = _crear_worker(tmp_path)

        assert "c1" not in w._datos_bancos
        assert "c1" not in w._ids_procesados

    def test_estado_con_barrier_completada_se_borra_del_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 1,
            "mensaje_eof_hex": None,
            "flush_iniciado": True,
            "barrera_completada": True,
        })
        _crear_worker(tmp_path)

        filepath = tmp_path / f"{NODE_PREFIX}_c1" / "estado.json"
        assert not filepath.exists()

    def test_estado_sin_barrier_completada_si_se_carga(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "Y", "max_amount": 7.0}},
            "ids_procesados": [],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert "c1" in w._datos_bancos


# ──────────────────────────────────────────────────────────────────
# Caso 4 — _ids_procesados evita doble procesamiento
# ──────────────────────────────────────────────────────────────────

class TestBankShardDedupPropio:

    def test_request_id_duplicado_no_modifica_estado(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "Test", "max_amount": 100.0, "account": "acc1", "accounts": ["acc1"]}},
            "ids_procesados": ["req-dup"],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        ack = MagicMock()
        nack = MagicMock()
        payload = {
            "client_id": "c1",
            "request_id": "req-dup",
            "batches": [{"header": {"schema": ["From Bank", "Account", "Amount Paid"], "client_id": "c1", "count": 1}, "payload": [["b1", "acc1", 999.0]]}],
        }
        w.procesar_payload("q2_transactions_1", "c1", payload, json.dumps(payload).encode(), ack, nack)

        assert w._datos_bancos["c1"]["b1"]["max_amount"] == 100.0
        ack.assert_called_once()
        nack.assert_not_called()

    def test_request_id_nuevo_modifica_estado(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {},
            "ids_procesados": [],
            "tx_eof_count": 0,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        payload = {
            "client_id": "c1",
            "request_id": "req-nuevo",
            "batches": [{"header": {"schema": ["From Bank", "Account", "Amount Paid"], "client_id": "c1", "count": 1}, "payload": [["b1", "acc1", 50.0]]}],
        }
        w.procesar_payload("q2_transactions_1", "c1", payload, json.dumps(payload).encode(), MagicMock(), MagicMock())

        assert "req-nuevo" in w._ids_procesados["c1"]
        assert "c1" in w._datos_bancos


# ──────────────────────────────────────────────────────────────────
# Caso 7 — Recovery con ambas colas cerradas dispara barrera diferida
# ──────────────────────────────────────────────────────────────────

class TestBankShardCaso7BarreraDiferida:

    def test_ambas_colas_cerradas_encola_barrera_para_iniciar(self, tmp_path):
        eof_msg = json.dumps({"client_id": "c1", "eof": True}).encode()
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "Test", "max_amount": 10.0}},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 1,
            "mensaje_eof_hex": eof_msg.hex(),
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert len(w._barreras_para_iniciar) == 1
        assert w._barreras_para_iniciar[0][0] == "c1"

    def test_al_iniciar_post_arranque_dispara_barrera_diferida(self, tmp_path):
        eof_msg = json.dumps({"client_id": "c1", "eof": True}).encode()
        _escribir_estado(tmp_path, "c1", {
            "bancos": {"b1": {"bank_name": "Test", "max_amount": 10.0}},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 1,
            "mensaje_eof_hex": eof_msg.hex(),
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        w.coordinador.iniciar_barrera = MagicMock()
        w.al_iniciar_post_arranque()

        w.coordinador.iniciar_barrera.assert_called_once_with("c1", eof_msg)
        assert len(w._barreras_para_iniciar) == 0

    def test_flush_iniciado_true_marca_eof_local_completo(self, tmp_path):
        eof_msg = json.dumps({"client_id": "c1", "eof": True}).encode()
        _escribir_estado(tmp_path, "c1", {
            "bancos": {},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 1,
            "mensaje_eof_hex": eof_msg.hex(),
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert w._estado_eof["c1"][CLAVE_FLUSH_INICIADO] is True

    def test_una_sola_cola_cerrada_no_encola_barrera(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "bancos": {},
            "ids_procesados": [],
            "tx_eof_count": 1,
            "bank_eof_count": 0,
            "mensaje_eof_hex": None,
            "flush_iniciado": False,
            "barrera_completada": False,
        })
        w = _crear_worker(tmp_path)

        assert len(w._barreras_para_iniciar) == 0
