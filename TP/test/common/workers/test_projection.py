"""
Tests para WorkerProyeccion
============================
Cubren la proyección de campos, normalización de IDs y propagación de EOF.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


def _make_worker(campos="From Bank,Amount Paid", int_fields=""):
    env = {
        "MOM_HOST": "rabbitmq",
        "NODE_PREFIX": "test_projection",
        "ID": "1",
        "TOTAL_WORKERS": "1",
        "INPUT_QUEUES": '["q_test_in"]',
        "OUTPUT_QUEUES": '["q_test_out"]',
        "CAMPOS": campos,
        "INT_FIELDS": int_fields,
        "HEARTBEAT_INTERVAL_SECONDS": "0",
    }
    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"):
        from workers.proyeccion.proyeccion import WorkerProyeccion
        w = WorkerProyeccion()
    w._enviar = MagicMock()
    return w


def _make_msg(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


# ------------------------------------------------------------------
# Tests: proyección de campos
# ------------------------------------------------------------------

class TestProyeccion:

    def test_conserva_solo_los_campos_indicados(self):
        w = _make_worker("From Bank,Amount Paid")
        payload = {
            "client_id": "abc",
            "From Bank": "10",
            "Amount Paid": 12.5,
            "Payment Currency": "USD",  # debe eliminarse
            "Timestamp": "2022-09-01",  # debe eliminarse
        }

        w.procesar_payload("q_in", "abc", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert set(enviado.keys()) == {"client_id", "From Bank", "Amount Paid"}

    def test_siempre_conserva_client_id(self):
        w = _make_worker("From Bank")
        payload = {"client_id": "xyz", "From Bank": "5", "Amount Paid": 99}

        w.procesar_payload("q_in", "xyz", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert enviado["client_id"] == "xyz"

    def test_campo_faltante_se_omite_sin_error(self):
        w = _make_worker("From Bank,Amount Paid,Timestamp")
        payload = {"client_id": "a", "From Bank": "3"}

        ack = MagicMock()
        w.procesar_payload("q_in", "a", payload, _make_msg(payload), ack, MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert "Amount Paid" not in enviado
        assert "Timestamp" not in enviado
        assert enviado["From Bank"] == "3"
        ack.assert_called_once()

    def test_valores_se_conservan_correctamente(self):
        w = _make_worker("From Bank,Amount Paid")
        payload = {"client_id": "b", "From Bank": "99", "Amount Paid": 49.99}

        w.procesar_payload("q_in", "b", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert enviado["From Bank"] == "99"
        assert enviado["Amount Paid"] == 49.99

    def test_hace_ack_tras_proyectar(self):
        w = _make_worker("From Bank")
        payload = {"client_id": "c", "From Bank": "1"}
        ack = MagicMock()
        nack = MagicMock()

        w.procesar_payload("q_in", "c", payload, _make_msg(payload), ack, nack)

        ack.assert_called_once()
        nack.assert_not_called()


# ------------------------------------------------------------------
# Tests: normalización de IDs
# ------------------------------------------------------------------

class TestNormalizacion:

    def test_normaliza_campo_a_int(self):
        w = _make_worker("From Bank,Amount Paid", int_fields="From Bank")
        payload = {"client_id": "d", "From Bank": "42", "Amount Paid": 10.0}

        w.procesar_payload("q_in", "d", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert enviado["From Bank"] == 42
        assert isinstance(enviado["From Bank"], int)

    def test_normaliza_solo_los_campos_indicados(self):
        w = _make_worker("From Bank,Amount Paid", int_fields="From Bank")
        payload = {"client_id": "e", "From Bank": "7", "Amount Paid": 5.5}

        w.procesar_payload("q_in", "e", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert isinstance(enviado["From Bank"], int)
        assert isinstance(enviado["Amount Paid"], float)

    def test_valor_no_numerico_se_conserva_como_esta(self):
        w = _make_worker("From Bank", int_fields="From Bank")
        payload = {"client_id": "f", "From Bank": "no-es-numero"}

        w.procesar_payload("q_in", "f", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert enviado["From Bank"] == "no-es-numero"

    def test_sin_int_fields_no_normaliza(self):
        w = _make_worker("From Bank")
        payload = {"client_id": "g", "From Bank": "123"}

        w.procesar_payload("q_in", "g", payload, _make_msg(payload), MagicMock(), MagicMock())

        msg_bytes = w._enviar.call_args[0][0]
        enviado = json.loads(msg_bytes)
        assert enviado["From Bank"] == "123"
        assert isinstance(enviado["From Bank"], str)


# ------------------------------------------------------------------
# Tests: ciclo de vida
# ------------------------------------------------------------------

class TestCicloDeVida:

    def test_al_cerrar_no_falla(self):
        w = _make_worker()
        w.al_cerrar()

    def test_nack_en_excepcion_inesperada(self):
        w = _make_worker("From Bank")
        w._enviar = MagicMock(side_effect=RuntimeError("fallo"))
        payload = {"client_id": "h", "From Bank": "1"}
        ack = MagicMock()
        nack = MagicMock()

        w.procesar_payload("q_in", "h", payload, _make_msg(payload), ack, nack)

        nack.assert_called_once()
        ack.assert_not_called()
