import json
from unittest.mock import MagicMock, patch, call

from workers.base.worker_base import WorkerBase
from common.middleware.middleware import MessageMiddlewareDisconnectedError


class WorkerDePrueba(WorkerBase):
    def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
        ack()

    def al_cerrar(self):
        pass


def _crear_worker():
    env = {
        "MOM_HOST": "rabbitmq",
        "NODE_PREFIX": "q5_filter_period",
        "ID": "2",
        "TOTAL_WORKERS": "1",
        "INPUT_QUEUES": '["q_in"]',
        "OUTPUT_QUEUES": '["q_out"]',
        "HEARTBEAT_INTERVAL_SECONDS": "5",
    }

    with patch.dict("os.environ", env):
        with patch("workers.base.worker_base.EnrutadorMensajes"), \
             patch("workers.base.worker_base.CoordinadorDistribuido"), \
             patch("workers.base.worker_base.signal.signal"):
            return WorkerDePrueba()


def test_inicia_thread_heartbeat_como_daemon():
    worker = _crear_worker()

    with patch("workers.base.latido.threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        worker._latido.iniciar()

    mock_thread_cls.assert_called_once_with(
        target=worker._latido._bucle,
        name="WorkerDePrueba-heartbeat",
        daemon=True,
    )
    mock_thread.start.assert_called_once_with()


def test_heartbeat_publica_en_cola_de_etapa_con_payload_esperado():
    worker = _crear_worker()
    worker._latido._evento_cierre = MagicMock()
    worker._latido._evento_cierre.is_set.return_value = False
    worker._latido._evento_cierre.wait.return_value = True

    heartbeat_queue = MagicMock()

    with patch(
        "workers.base.latido.middleware.MessageMiddlewareQueueRabbitMQ",
        return_value=heartbeat_queue,
    ) as mock_queue_cls, patch("workers.base.latido.time.time", return_value=123.0):
        worker._latido._bucle()

    mock_queue_cls.assert_called_once_with("rabbitmq", "heartbeat.q5_filter_period")
    heartbeat_queue.send.assert_called_once()
    worker._latido._evento_cierre.wait.assert_called_once_with(5.0)
    heartbeat_queue.close.assert_called_once_with()

    payload = json.loads(heartbeat_queue.send.call_args[0][0].decode("utf-8"))
    assert payload == {
        "etapa": "q5_filter_period",
        "instancia": "02",
        "timestamp": 123.0,
    }


def test_registro_en_watchdog_usa_formato_zero_padded():
    """El registro en el exchange del watchdog debe usar el mismo formato
    de instancia que el heartbeat (zero-padded '02'), para que el detector
    no cree entries duplicadas que generen falsos positivos."""
    worker = _crear_worker()

    mock_cola = MagicMock()

    with patch(
        "workers.base.worker_base.MessageMiddlewareQueueRabbitMQ",
        return_value=mock_cola,
    ):
        worker._registrar_en_watchdog()

    mock_cola.channel.basic_publish.assert_called_once()
    call_kwargs = mock_cola.channel.basic_publish.call_args
    body = json.loads(call_kwargs[1]["body"].decode("utf-8") if "body" in (call_kwargs[1] or {}) else call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]["body"])
    assert body["instancia"] == "02", f"Registro envía '{body['instancia']}' pero heartbeat envía '02' — mismatch causa falsos positivos"
    assert body["etapa"] == "q5_filter_period"


def test_registro_y_heartbeat_usan_mismo_formato_instancia():
    """Garantiza que el formato de instancia sea idéntico entre
    _registrar_en_watchdog y Latido._bucle."""
    worker = _crear_worker()

    # Capturar payload de registro
    mock_cola_reg = MagicMock()
    with patch(
        "workers.base.worker_base.MessageMiddlewareQueueRabbitMQ",
        return_value=mock_cola_reg,
    ):
        worker._registrar_en_watchdog()

    registro_body = json.loads(
        mock_cola_reg.channel.basic_publish.call_args[1]["body"].decode("utf-8")
    )

    # Capturar payload de heartbeat
    worker._latido._evento_cierre = MagicMock()
    worker._latido._evento_cierre.is_set.return_value = False
    worker._latido._evento_cierre.wait.return_value = True

    mock_cola_hb = MagicMock()
    with patch(
        "workers.base.latido.middleware.MessageMiddlewareQueueRabbitMQ",
        return_value=mock_cola_hb,
    ):
        worker._latido._bucle()

    heartbeat_body = json.loads(mock_cola_hb.send.call_args[0][0].decode("utf-8"))

    assert registro_body["instancia"] == heartbeat_body["instancia"], \
        f"Registro usa '{registro_body['instancia']}' pero heartbeat usa '{heartbeat_body['instancia']}'"


class TestRetryHiloConsumo:

    def test_reconecta_tras_desconexion_transitoria(self):
        worker = _crear_worker()
        mock_cola = MagicMock()
        intentos = []

        def start_consuming_side_effect(cb):
            intentos.append(1)
            if len(intentos) <= 2:
                raise MessageMiddlewareDisconnectedError("conexión perdida")

        mock_cola.start_consuming = start_consuming_side_effect
        mock_cola._reconnect = MagicMock()

        with patch("workers.base.worker_base.time.sleep"):
            worker._ejecutar_hilo_consumo("q_in", mock_cola)

        assert len(intentos) == 3
        assert mock_cola._reconnect.call_count == 2

    def test_no_reintenta_si_cierre_solicitado(self):
        worker = _crear_worker()
        mock_cola = MagicMock()

        def desconectar_y_cerrar(cb):
            worker._cierre_solicitado = True
            raise MessageMiddlewareDisconnectedError("conexión perdida")

        mock_cola.start_consuming = MagicMock(side_effect=desconectar_y_cerrar)

        worker._ejecutar_hilo_consumo("q_in", mock_cola)

        mock_cola.start_consuming.assert_called_once()

    def test_exit_tras_agotar_reintentos(self):
        worker = _crear_worker()
        mock_cola = MagicMock()
        mock_cola.start_consuming = MagicMock(
            side_effect=MessageMiddlewareDisconnectedError("conexión perdida")
        )
        mock_cola._reconnect = MagicMock()

        with patch("workers.base.worker_base.time.sleep"), \
             patch("workers.base.worker_base.os._exit", side_effect=SystemExit) as mock_exit:
            try:
                worker._ejecutar_hilo_consumo("q_in", mock_cola)
            except SystemExit:
                pass

        mock_exit.assert_called_once_with(1)
        assert mock_cola._reconnect.call_count == worker._MAX_REINTENTOS_CONSUMO

    def test_exit_si_reconnect_falla(self):
        worker = _crear_worker()
        mock_cola = MagicMock()
        mock_cola.start_consuming = MagicMock(
            side_effect=MessageMiddlewareDisconnectedError("conexión perdida")
        )
        mock_cola._reconnect = MagicMock(side_effect=Exception("rabbitmq caído"))

        with patch("workers.base.worker_base.time.sleep"), \
             patch("workers.base.worker_base.os._exit", side_effect=SystemExit) as mock_exit:
            try:
                worker._ejecutar_hilo_consumo("q_in", mock_cola)
            except SystemExit:
                pass

        mock_exit.assert_called_once_with(1)
        mock_cola._reconnect.assert_called_once()

    def test_error_no_disconnected_sale_inmediatamente(self):
        worker = _crear_worker()
        mock_cola = MagicMock()
        mock_cola.start_consuming = MagicMock(
            side_effect=RuntimeError("error inesperado")
        )

        with patch("workers.base.worker_base.os._exit", side_effect=SystemExit) as mock_exit:
            try:
                worker._ejecutar_hilo_consumo("q_in", mock_cola)
            except SystemExit:
                pass

        mock_exit.assert_called_once_with(1)
        mock_cola.start_consuming.assert_called_once()

    def test_backoff_exponencial_en_reintentos(self):
        worker = _crear_worker()
        mock_cola = MagicMock()
        llamadas_sleep = []

        def start_side_effect(cb):
            if len(llamadas_sleep) < 3:
                raise MessageMiddlewareDisconnectedError("conexión perdida")

        mock_cola.start_consuming = start_side_effect
        mock_cola._reconnect = MagicMock()

        def capturar_sleep(s):
            llamadas_sleep.append(s)

        with patch("workers.base.worker_base.time.sleep", side_effect=capturar_sleep):
            worker._ejecutar_hilo_consumo("q_in", mock_cola)

        assert llamadas_sleep == [2, 4, 8]
