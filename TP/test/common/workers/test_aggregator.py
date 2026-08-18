"""
Tests para ContadorDistintoWorker
======================================
Cubren la agrupación por campos, acumulación de valores distintos, filtrado
por EXPECTED_COUNT y los modos de emisión aggregate y explode.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


def _make_worker(
    tmp_path,
    monkeypatch,
    group_fields="bank",
    value_fields="destination",
    expected=2,
    emit_mode="aggregate",
    count_field="Amount Transactions",
    operator="eq",
):
    monkeypatch.setattr("workers.contador_distinto.contador_distinto.BASE_DIR", str(tmp_path))
    env = {
        "MOM_HOST": "rabbitmq",
        "NODE_PREFIX": "test_gdc",
        "ID": "1",
        "TOTAL_WORKERS": "1",
        "INPUT_QUEUES": '["q_test_in"]',
        "OUTPUT_QUEUES": '["q_test_out"]',
        "HEARTBEAT_INTERVAL_SECONDS": "0",
        "GROUP_FIELDS": group_fields,
        "VALUE_FIELDS": value_fields,
        "EXPECTED_COUNT": str(expected),
        "EMIT_MODE": emit_mode,
        "COUNT_OUTPUT_FIELD": count_field,
        "COMPARISON_OPERATOR": operator,
    }
    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"):
        from workers.contador_distinto.contador_distinto import ContadorDistintoWorker
        w = ContadorDistintoWorker()
    w._enviar = MagicMock()
    return w


def _msg(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _procesar(worker, client_id, request_id, **campos):
    payload = {"client_id": client_id, "request_id": request_id, **campos}
    worker.procesar_payload("q_in", client_id, payload, _msg(payload), MagicMock(), MagicMock())


# ------------------------------------------------------------------
# Tests: acumulación de grupos y valores distintos
# ------------------------------------------------------------------

class TestAgregar:

    def test_acumula_valores_distintos_por_grupo(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="A", destination="y")

        assert len(w.acumulador._grupos["c1"][("A",)]) == 2

    def test_valores_duplicados_no_se_cuentan_doble(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="A", destination="x")

        assert len(w.acumulador._grupos["c1"][("A",)]) == 1

    def test_grupos_distintos_se_acumulan_separados(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="B", destination="x")

        assert ("A",) in w.acumulador._grupos["c1"]
        assert ("B",) in w.acumulador._grupos["c1"]

    def test_clientes_distintos_grupos_independientes(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c2", "r2", bank="A", destination="y")

        assert len(w.acumulador._grupos["c1"][("A",)]) == 1
        assert len(w.acumulador._grupos["c2"][("A",)]) == 1


# ------------------------------------------------------------------
# Tests: flush en modo aggregate
# ------------------------------------------------------------------

class TestFlushAggregate:

    def test_emite_solo_grupos_con_expected_count(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=2)
        # Grupo A: 2 destinos → debe emitirse
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="A", destination="y")
        # Grupo B: 1 destino → no debe emitirse
        _procesar(w, "c1", "r3", bank="B", destination="x")

        w.al_completar_cliente("c1")

        assert w._enviar.call_count == 1
        emitido = json.loads(w._enviar.call_args[0][0])
        records = emitido["batches"][0]["payload"]
        assert len(records) == 1
        assert records[0][0] == "A"

    def test_schema_incluye_count_output_field(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=1, count_field="mis_conteos")
        _procesar(w, "c1", "r1", bank="A", destination="x")

        w.al_completar_cliente("c1")

        emitido = json.loads(w._enviar.call_args[0][0])
        schema = emitido["batches"][0]["header"]["schema"]
        assert "mis_conteos" in schema

    def test_valor_count_es_correcto(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=3)
        for dest in ["x", "y", "z"]:
            _procesar(w, "c1", f"r_{dest}", bank="A", destination=dest)

        w.al_completar_cliente("c1")

        emitido = json.loads(w._enviar.call_args[0][0])
        # Último campo del record es el count
        record = emitido["batches"][0]["payload"][0]
        assert record[-1] == 3

    def test_operator_gt_filtra_correctamente(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=2, operator="gt")
        # Grupo A: 3 > 2 → debe emitirse
        for dest in ["x", "y", "z"]:
            _procesar(w, "c1", f"r_A_{dest}", bank="A", destination=dest)
        # Grupo B: 2 == 2, no > 2 → no debe emitirse
        for dest in ["x", "y"]:
            _procesar(w, "c1", f"r_B_{dest}", bank="B", destination=dest)

        w.al_completar_cliente("c1")

        emitido = json.loads(w._enviar.call_args[0][0])
        records = emitido["batches"][0]["payload"]
        assert len(records) == 1
        assert records[0][0] == "A"


# ------------------------------------------------------------------
# Tests: flush en modo explode
# ------------------------------------------------------------------

class TestFlushExplode:

    def test_emite_un_registro_por_valor_distinto(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=2, emit_mode="explode")
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="A", destination="y")

        w.al_completar_cliente("c1")

        emitido = json.loads(w._enviar.call_args[0][0])
        records = emitido["batches"][0]["payload"]
        assert len(records) == 2

    def test_no_emite_grupos_que_no_cumplen_expected(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=3, emit_mode="explode")
        # Solo 2 valores → no se emite
        _procesar(w, "c1", "r1", bank="A", destination="x")
        _procesar(w, "c1", "r2", bank="A", destination="y")

        w.al_completar_cliente("c1")

        w._enviar.assert_not_called()


# ------------------------------------------------------------------
# Tests: ciclo de vida
# ------------------------------------------------------------------

class TestCicloDeVida:

    def test_al_cerrar_no_falla(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        w.al_cerrar()

    def test_al_desconectar_cliente_limpia_estado(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch)
        _procesar(w, "c1", "r1", bank="A", destination="x")

        w.al_desconectar_cliente("c1")

        assert "c1" not in w.acumulador._grupos

    def test_flush_limpia_estado_interno(self, tmp_path, monkeypatch):
        w = _make_worker(tmp_path, monkeypatch, expected=1)
        _procesar(w, "c1", "r1", bank="A", destination="x")

        w.al_completar_cliente("c1")

        assert "c1" not in w.acumulador._grupos
