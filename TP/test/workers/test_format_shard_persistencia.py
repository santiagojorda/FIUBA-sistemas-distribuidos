"""
Tests de persistencia para FormatShardWorker
=============================================
Cubren:
  - Caso 1: recovery del estado desde disco al reiniciarse
  - Caso 4: dedup propio (processed_request_ids) en ventana crash-entre-persist-y-ack
  - Caso 7: recovery con ambas fases cerradas y cache procesado dispara barrera diferida
  - Caso 8: barrier_completada previene re-flush tras caída
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from common.persistencia import PersistidorEstado


BASE_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "q3_format_shard",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q3_temprano_1", "q3_tardio_1"]',
    "OUTPUT_QUEUES": '["q3_results"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
}

NODE_PREFIX = "format_shard_1"


def _escribir_estado(tmp_path, client_id, estado):
    PersistidorEstado(f"{NODE_PREFIX}_{client_id}", base_dir=str(tmp_path)).guardar(estado)


def _escribir_cache(tmp_path, client_id, lineas):
    directory = tmp_path / f"{NODE_PREFIX}_{client_id}"
    os.makedirs(directory, exist_ok=True)
    with open(directory / "cache_tardio.jsonl", "w") as f:
        for linea in lineas:
            f.write(json.dumps(linea) + "\n")


def _crear_worker(tmp_path, extra_env=None):
    import format_shard as mod
    import config_format
    env = {**BASE_ENV, **(extra_env or {})}

    def patched_init(self, nid):
        self.base_dir = str(tmp_path)
        self.prefijo_nodo = NODE_PREFIX

    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"), \
         patch.object(config_format.ConfigFormateador, "__init__", patched_init):
        w = mod.FormateadorShardWorker()
    return w


# ──────────────────────────────────────────────────────────────────
# Caso 1 — Recovery de estado desde disco
# ──────────────────────────────────────────────────────────────────

class TestFormatShardRecovery:

    def test_carga_estado_parcial_desde_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True,
            "tardio_cerrado": False,
            "promedios_listos": True,
            "promedios": {"CreditCard": 150.0},
            "datos_temprano": {"CreditCard": {"suma": 15000, "count": 100}},
            "mensaje_eof_hex": None,
            "cache_procesado": False,
            "barrera_completada": False,
            "ids_procesados": ["r1", "r2"],
        })
        w = _crear_worker(tmp_path)

        assert "c1" in w.estado_clientes
        estado = w.estado_clientes["c1"]
        assert estado["temprano_cerrado"] is True
        assert estado["tardio_cerrado"] is False
        assert estado["promedios"]["CreditCard"] == 150.0
        assert estado["ids_procesados"] == {"r1", "r2"}

    def test_arranca_limpio_sin_estado_en_disco(self, tmp_path):
        w = _crear_worker(tmp_path)
        assert "c1" not in w.estado_clientes

    def test_multiples_clientes_se_recuperan_independientemente(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        _escribir_estado(tmp_path, "c2", {
            "temprano_cerrado": False, "tardio_cerrado": True,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": ["x"],
        })
        w = _crear_worker(tmp_path)

        assert w.estado_clientes["c1"]["temprano_cerrado"] is True
        assert w.estado_clientes["c2"]["tardio_cerrado"] is True
        assert w.estado_clientes["c2"]["ids_procesados"] == {"x"}

    def test_eof_mensaje_se_recupera_como_bytes(self, tmp_path):
        eof_msg = b'{"client_id": "c1", "eof": true}'
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": eof_msg.hex(),
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        assert w.estado_clientes["c1"]["mensaje_eof"] == eof_msg

    def test_request_ids_de_cache_jsonl_se_agregan_en_recovery(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": False, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": ["r1"],
        })
        _escribir_cache(tmp_path, "c1", [
            {"request_id": "r2", "schema": ["col"], "records": [["v"]]},
            {"request_id": "r3", "schema": ["col"], "records": [["v"]]},
        ])
        w = _crear_worker(tmp_path)

        assert w.estado_clientes["c1"]["ids_procesados"] == {"r1", "r2", "r3"}


# ──────────────────────────────────────────────────────────────────
# Caso 8 — barrier_completada previene re-flush
# ──────────────────────────────────────────────────────────────────

class TestFormatShardBarrierCompletada:

    def test_estado_con_barrier_completada_no_se_carga_en_memoria(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": True,
            "promedios_listos": True, "promedios": {"CC": 100.0},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": True, "barrera_completada": True,
            "ids_procesados": ["r1"],
        })
        w = _crear_worker(tmp_path)

        assert "c1" not in w.estado_clientes

    def test_estado_con_barrier_completada_se_borra_del_disco(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": True,
            "promedios_listos": True, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": True, "barrera_completada": True,
            "ids_procesados": [],
        })
        _crear_worker(tmp_path)

        filepath = tmp_path / f"{NODE_PREFIX}_c1" / "estado.json"
        assert not filepath.exists()

    def test_estado_sin_barrier_completada_si_se_carga(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        assert "c1" in w.estado_clientes


# ──────────────────────────────────────────────────────────────────
# Caso 4 — processed_request_ids evita doble procesamiento
# ──────────────────────────────────────────────────────────────────

class TestFormatShardDedupPropio:

    def test_request_id_duplicado_no_procesa_temprano(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": False, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {"CC": {"suma": 10000, "count": 1}},
            "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": ["req-dup"],
        })
        w = _crear_worker(tmp_path)

        ack = MagicMock()
        nack = MagicMock()
        payload = {
            "client_id": "c1",
            "request_id": "req-dup",
            "batches": [{"header": {"schema": ["Payment Format", "Amount Paid"], "client_id": "c1", "count": 1}, "payload": [["CC", 999.0]]}],
        }
        w.procesar_payload("q3_temprano_1", "c1", payload, json.dumps(payload).encode(), ack, nack)

        assert w.estado_clientes["c1"]["datos_temprano"]["CC"]["suma"] == 10000
        ack.assert_called_once()
        nack.assert_not_called()

    def test_request_id_nuevo_acumula_temprano_y_persiste(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": False, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {"CC": {"suma": 10000, "count": 1}},
            "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        payload = {
            "client_id": "c1",
            "request_id": "req-nuevo",
            "batches": [{"header": {"schema": ["Payment Format", "Amount Paid"], "client_id": "c1", "count": 1}, "payload": [["CC", 50.0]]}],
        }
        w.procesar_payload("q3_temprano_1", "c1", payload, json.dumps(payload).encode(), MagicMock(), MagicMock())

        assert "req-nuevo" in w.estado_clientes["c1"]["ids_procesados"]
        assert w.estado_clientes["c1"]["datos_temprano"]["CC"]["suma"] == 15000

    def test_request_id_duplicado_no_duplica_en_cache_tardio(self, tmp_path):
        _escribir_cache(tmp_path, "c1", [
            {"request_id": "req-dup", "schema": ["col"], "records": [["v"]]},
        ])
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": False, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": ["req-dup"],
        })
        w = _crear_worker(tmp_path)

        ack = MagicMock()
        payload = {
            "client_id": "c1",
            "request_id": "req-dup",
            "batches": [{"header": {"schema": ["From Bank", "Amount Paid", "Payment Format", "Account"], "client_id": "c1", "count": 1}, "payload": [["b1", 10.0, "CC", "acc1"]]}],
        }
        w.procesar_payload("q3_tardio_1", "c1", payload, json.dumps(payload).encode(), ack, MagicMock())

        ack.assert_called_once()
        cache_path = tmp_path / f"{NODE_PREFIX}_c1" / "cache_tardio.jsonl"
        with open(cache_path) as f:
            lines = [l for l in f.readlines() if l.strip()]
        assert len(lines) == 1


# ──────────────────────────────────────────────────────────────────
# Caso 7 — Recovery con ambas fases cerradas dispara barrera diferida
# ──────────────────────────────────────────────────────────────────

class TestFormatShardCaso7BarreraDiferida:

    def test_ambas_fases_cerradas_y_cache_procesado_encola_barrera(self, tmp_path):
        eof_msg = b'{"client_id": "c1", "eof": true}'
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": True,
            "promedios_listos": True, "promedios": {"CC": 100.0},
            "datos_temprano": {}, "mensaje_eof_hex": eof_msg.hex(),
            "cache_procesado": True, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        assert len(w._barreras_para_iniciar) == 1
        assert w._barreras_para_iniciar[0][0] == "c1"

    def test_al_iniciar_post_arranque_dispara_barrera_diferida(self, tmp_path):
        eof_msg = b'{"client_id": "c1", "eof": true}'
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": True,
            "promedios_listos": True, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": eof_msg.hex(),
            "cache_procesado": True, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        w.coordinador.iniciar_barrera = MagicMock()
        w.al_iniciar_post_arranque()

        w.coordinador.iniciar_barrera.assert_called_once_with("c1", eof_msg)
        assert len(w._barreras_para_iniciar) == 0

    def test_solo_temprano_cerrado_no_encola_barrera(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": False,
            "promedios_listos": False, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        assert len(w._barreras_para_iniciar) == 0

    def test_cache_no_procesado_no_encola_barrera(self, tmp_path):
        _escribir_estado(tmp_path, "c1", {
            "temprano_cerrado": True, "tardio_cerrado": True,
            "promedios_listos": True, "promedios": {},
            "datos_temprano": {}, "mensaje_eof_hex": None,
            "cache_procesado": False, "barrera_completada": False,
            "ids_procesados": [],
        })
        w = _crear_worker(tmp_path)

        assert len(w._barreras_para_iniciar) == 0
