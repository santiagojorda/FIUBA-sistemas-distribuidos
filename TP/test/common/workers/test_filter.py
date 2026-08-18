"""
Tests para GenericFilterWorker
==============================
Cubren el filtrado de registros planos con distintos operadores y
propagación de EOF.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


def _crear_worker(filter_field: str, filter_value: str, filter_operator: str = "igual"):
    env = {
        "MOM_HOST": "rabbitmq",
        "NODE_PREFIX": "test_filter",
        "ID": "1",
        "TOTAL_WORKERS": "1",
        "INPUT_QUEUES": '["q_test_in"]',
        "OUTPUT_QUEUES": "[]",
        "HEARTBEAT_INTERVAL_SECONDS": "0",
        "CAMPO_FILTRO": filter_field,
        "VALOR_FILTRO": filter_value,
        "OPERADOR_FILTRO": filter_operator,
    }
    with patch.dict("os.environ", env), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"):
        from workers.filtro.filtro import GenericFilterWorker
        w = GenericFilterWorker()
    return w


def _make_msg(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


# ------------------------------------------------------------------
# Tests: inicialización
# ------------------------------------------------------------------

class TestInicializacion:

    def test_falta_filter_field_lanza_error(self):
        env = {
            "MOM_HOST": "rabbitmq",
            "NODE_PREFIX": "test_filter",
            "ID": "1",
            "TOTAL_WORKERS": "1",
            "INPUT_QUEUES": '["q_test_in"]',
            "OUTPUT_QUEUES": "[]",
            "HEARTBEAT_INTERVAL_SECONDS": "0",
            # CAMPO_FILTRO omitido
            "VALOR_FILTRO": "USD",
        }
        with patch.dict("os.environ", env, clear=False), \
             patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
             patch("common.middleware.FanoutQueueRabbitMQ"), \
             patch("common.middleware.FanoutExchangeRabbitMQ"):
            from workers.filtro.filtro import GenericFilterWorker
            with pytest.raises(KeyError):
                GenericFilterWorker()


# ------------------------------------------------------------------
# Tests: filtrado de registros
# ------------------------------------------------------------------

class TestProcesarMensaje:

    @pytest.mark.parametrize(
        "filter_field,filter_value,filter_operator,payload,espera_envio",
        [
            ("payment_currency", "USD", "igual",  {"client_id": "c1", "payment_currency": "USD"}, True),
            ("payment_currency", "USD", "igual",  {"client_id": "c1", "payment_currency": "EUR"}, False),
            ("amount_paid",      "50",  "menor", {"client_id": "c1", "amount_paid": 30},          True),
            ("amount_paid",      "50",  "menor", {"client_id": "c1", "amount_paid": 60},          False),
        ],
    )
    def test_filtro_aplica_segun_configuracion(self, filter_field, filter_value, filter_operator, payload, espera_envio):
        worker = _crear_worker(filter_field, filter_value, filter_operator)
        ack  = MagicMock()
        nack = MagicMock()
        msg  = _make_msg(payload)

        with patch.object(worker, "_enviar") as enviar:
            worker.procesar_payload("q_in", payload["client_id"], payload, msg, ack, nack)

        if espera_envio:
            enviar.assert_called_once()
        else:
            enviar.assert_not_called()

        ack.assert_called_once()
        nack.assert_not_called()

    def test_campo_faltante_se_descarta_con_ack(self):
        worker = _crear_worker("payment_currency", "USD", "igual")
        ack  = MagicMock()
        nack = MagicMock()
        payload = {"client_id": "c1", "otro_campo": "valor"}
        msg  = _make_msg(payload)

        with patch.object(worker, "_enviar") as enviar:
            worker.procesar_payload("q_in", "c1", payload, msg, ack, nack)

        enviar.assert_not_called()
        ack.assert_called_once()
        nack.assert_not_called()

    def test_eof_se_reenvia_via_enviar(self):
        worker = _crear_worker("payment_currency", "USD", "igual")
        ack  = MagicMock()
        nack = MagicMock()
        payload = {"client_id": "c1", "EOF": True}
        msg  = _make_msg(payload)

        with patch.object(worker, "_enviar") as enviar:
            worker.procesar_payload("q_in", "c1", payload, msg, ack, nack)

        enviar.assert_called_once_with(msg)
        ack.assert_called_once()
        nack.assert_not_called()

    def test_al_cerrar_no_falla(self):
        worker = _crear_worker("payment_currency", "USD", "igual")
        worker.al_cerrar()
