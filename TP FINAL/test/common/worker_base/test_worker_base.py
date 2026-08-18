import signal
import pytest
from unittest.mock import MagicMock, patch, call

from workers.base.worker_base import WorkerBase

TEST_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "test",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q_test_in"]',
    "OUTPUT_QUEUES": "[]",
    "HEARTBEAT_INTERVAL_SECONDS": "0",
}

INPUT_QUEUE_NAME = "q_test_in"


class WorkerDePrueba(WorkerBase):

    def __init__(self):
        self._mensajes_procesados = []
        self._al_cerrar_llamado = False
        super().__init__()

    def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
        self._mensajes_procesados.append(mensaje_original)
        ack()

    def al_cerrar(self):
        self._al_cerrar_llamado = True


@pytest.fixture(autouse=True)
def mock_middleware():
    with patch.dict("os.environ", TEST_ENV, clear=False), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ") as mock_queue_cls_common, \
         patch("workers.base.worker_base.MessageMiddlewareQueueRabbitMQ") as mock_queue_cls_worker, \
         patch("common.middleware.FanoutQueueRabbitMQ") as mock_fanout_queue_cls, \
         patch("common.middleware.FanoutExchangeRabbitMQ") as mock_exchange_cls:

        mock_input_queue   = MagicMock()
        mock_control_queue = MagicMock()
        mock_exchange      = MagicMock()

        def queue_side_effect(host, queue_name, *args, **kwargs):
            if queue_name == "watchdog.registro.temp":
                return MagicMock()
            return mock_input_queue

        mock_queue_cls_common.side_effect = queue_side_effect
        mock_queue_cls_worker.side_effect = queue_side_effect
        mock_fanout_queue_cls.return_value = mock_control_queue
        mock_exchange_cls.return_value   = mock_exchange

        yield {
            "input_queue":        mock_input_queue,
            "control_queue":      mock_control_queue,
            "exchange":           mock_exchange,
            "queue_cls":          mock_queue_cls_common,
            "fanout_queue_cls":   mock_fanout_queue_cls,
            "exchange_cls":       mock_exchange_cls,
        }


@pytest.fixture
def worker():
    return WorkerDePrueba()


class TestCicloDeVida:

    def test_iniciar_llama_start_consuming_en_input_queue(self, worker, mock_middleware):
        worker.iniciar()
        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].start_consuming.assert_called_once()

    def test_iniciar_llama_start_consuming_en_control_queue(self, worker, mock_middleware):
        worker.iniciar()
        worker.coordinador._transporte.cola.start_consuming.assert_called_once()

    def test_iniciar_cierra_input_queue_al_terminar(self, worker, mock_middleware):
        worker.iniciar()
        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].close.assert_called_once()

    def test_iniciar_cierra_control_queue_al_terminar(self, worker, mock_middleware):
        worker.iniciar()
        worker.coordinador._transporte.cola.close.assert_called_once()

    def test_iniciar_cierra_control_exchange_al_terminar(self, worker, mock_middleware):
        worker.iniciar()
        worker.coordinador._transporte.exchange.close.assert_called_once()

    def test_iniciar_llama_al_cerrar(self, worker, mock_middleware):
        worker.iniciar()
        assert worker._al_cerrar_llamado is True

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_cierre_ocurre_aunque_start_consuming_lance_excepcion(self, worker, mock_middleware):
        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].start_consuming.side_effect = RuntimeError("fallo de red")

        with patch("workers.base.worker_base.os._exit"):
            worker.iniciar()

        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].close.assert_called_once()


class TestShutdownGraceful:

    def test_sigterm_setea_cierre_solicitado(self, worker):
        worker._manejar_senal_cierre(signal.SIGTERM, None)
        assert worker._cierre_solicitado is True

    def test_sigint_setea_cierre_solicitado(self, worker):
        worker._manejar_senal_cierre(signal.SIGINT, None)
        assert worker._cierre_solicitado is True

    def test_sigterm_llama_stop_consuming_en_input_queue(self, worker):
        worker._manejar_senal_cierre(signal.SIGTERM, None)
        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].stop_consuming.assert_called_once()

    def test_sigterm_llama_stop_consuming_en_control_queue(self, worker):
        worker._manejar_senal_cierre(signal.SIGTERM, None)
        worker.coordinador._transporte.cola.stop_consuming.assert_called_once()

    def test_sigterm_notifica_condicion_pendiente(self, worker):
        notificado = []

        def esperar():
            with worker.condicion_pendiente:
                worker.condicion_pendiente.wait(timeout=2)
                notificado.append(True)

        import threading
        t = threading.Thread(target=esperar)
        t.start()
        worker._manejar_senal_cierre(signal.SIGTERM, None)
        t.join(timeout=3)

        assert notificado == [True]

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_iniciar_no_propaga_excepcion_si_cierre_fue_solicitado(self, worker, mock_middleware):
        def simular_consumo_interrumpido(callback):
            worker._cierre_solicitado = True
            raise Exception("consumo interrumpido por cierre")

        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].start_consuming.side_effect = simular_consumo_interrumpido
        worker.iniciar()


class TestCallbackInterno:

    def test_mensaje_normal_llama_a_procesar_mensaje(self, worker):
        ack  = MagicMock()
        nack = MagicMock()
        mensaje = b'{"client_id": "c1", "monto": 10}'

        worker._callback_interno(INPUT_QUEUE_NAME, mensaje, ack, nack)

        assert mensaje in worker._mensajes_procesados
        ack.assert_called_once()
        nack.assert_not_called()

    def test_cierre_solicitado_hace_nack_sin_procesar(self, worker):
        worker._cierre_solicitado = True
        ack  = MagicMock()
        nack = MagicMock()

        worker._callback_interno(INPUT_QUEUE_NAME, b'{"client_id": "c1"}', ack, nack)

        nack.assert_called_once()
        ack.assert_not_called()
        assert len(worker._mensajes_procesados) == 0

    def test_excepcion_en_procesar_mensaje_llama_nack(self, mock_middleware):
        class WorkerQueExplota(WorkerBase):
            def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
                raise ValueError("error de negocio")
            def al_cerrar(self):
                pass

        w   = WorkerQueExplota()
        ack  = MagicMock()
        nack = MagicMock()

        w._callback_interno(INPUT_QUEUE_NAME, b'{"client_id": "c1", "dato": 1}', ack, nack)

        nack.assert_called_once()
        ack.assert_not_called()

    def test_excepcion_en_procesar_mensaje_no_tira_el_worker(self, mock_middleware):
        class WorkerQueExplota(WorkerBase):
            def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
                raise ValueError("error de negocio")
            def al_cerrar(self):
                pass

        w = WorkerQueExplota()

        w._callback_interno(INPUT_QUEUE_NAME, b'{"client_id": "c1", "dato": 1}', MagicMock(), MagicMock())

    def test_multiples_mensajes_se_procesan_en_orden(self, worker):
        mensajes = [
            b'{"client_id": "c1", "seq": 1}',
            b'{"client_id": "c1", "seq": 2}',
            b'{"client_id": "c1", "seq": 3}',
        ]

        for msg in mensajes:
            worker._callback_interno(INPUT_QUEUE_NAME, msg, MagicMock(), MagicMock())

        assert worker._mensajes_procesados == mensajes


class TestAlCerrar:

    def test_al_cerrar_se_ejecuta_antes_de_cerrar_middleware(self, mock_middleware):
        orden = []

        class WorkerConOrden(WorkerBase):
            def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
                ack()
            def al_cerrar(self):
                orden.append("al_cerrar")

        w = WorkerConOrden()
        for q in w.enrutador.colas_entrada.values():
            q.close.side_effect = lambda: orden.append("close")
        w._cerrar()

        assert orden[0] == "al_cerrar"
        assert "close" in orden

    def test_excepcion_en_al_cerrar_no_impide_cerrar_middleware(self, mock_middleware):
        class WorkerAlCerrarFalla(WorkerBase):
            def procesar_payload(self, nombre_cola, client_id, payload, mensaje_original, ack, nack):
                ack()
            def al_cerrar(self):
                raise RuntimeError("fallo en cleanup")

        w = WorkerAlCerrarFalla()
        w._cerrar()

        for q in w.enrutador.colas_entrada.values():
            q.close.assert_called_once()
        w.coordinador._transporte.cola.close.assert_called_once()
        w.coordinador._transporte.exchange.close.assert_called_once()


class TestZombiePrevention:

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_excepcion_inesperada_en_hilo_consumo_llama_os_exit(self, worker, mock_middleware):
        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].start_consuming.side_effect = RuntimeError("ConnectionResetError")

        with patch("workers.base.worker_base.os._exit") as mock_exit:
            worker.iniciar()

        mock_exit.assert_called_once_with(1)

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_excepcion_en_hilo_consumo_no_llama_os_exit_si_cierre_solicitado(self, worker, mock_middleware):
        def consumo_interrumpido_por_cierre(callback):
            worker._cierre_solicitado = True
            raise RuntimeError("consumo interrumpido por cierre")

        worker.enrutador.colas_entrada[INPUT_QUEUE_NAME].start_consuming.side_effect = consumo_interrumpido_por_cierre

        with patch("workers.base.worker_base.os._exit") as mock_exit:
            worker.iniciar()

        mock_exit.assert_not_called()

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_excepcion_inesperada_en_hilo_coordinador_llama_os_exit(self, worker, mock_middleware):
        worker.coordinador.iniciar_consumo = MagicMock(side_effect=RuntimeError("fallo coordinador"))

        with patch("workers.base.worker_base.os._exit") as mock_exit:
            worker.iniciar()

        mock_exit.assert_called_once_with(1)

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_excepcion_en_hilo_coordinador_no_llama_os_exit_si_cierre_solicitado(self, worker, mock_middleware):
        def coordinador_interrumpido_por_cierre():
            worker._cierre_solicitado = True
            raise RuntimeError("coordinador cerrado por señal")

        worker.coordinador.iniciar_consumo = MagicMock(side_effect=coordinador_interrumpido_por_cierre)

        with patch("workers.base.worker_base.os._exit") as mock_exit:
            worker.iniciar()

        mock_exit.assert_not_called()


class TestSesionInvalidada:
    """Verifica que datos de una sesión desconectada se descartan,
    evitando la race condition DISCONNECT vs datos en vuelo."""

    def test_datos_de_sesion_invalidada_se_descartan(self, worker):
        ack = MagicMock()
        nack = MagicMock()

        disconnect_msg = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "abc123"}'
        worker._callback_interno(INPUT_QUEUE_NAME, disconnect_msg, MagicMock(), MagicMock())

        dato_viejo = b'{"client_id": "c1", "request_id": "c1:abc123:q:1", "dato": 1}'
        worker._callback_interno(INPUT_QUEUE_NAME, dato_viejo, ack, nack)

        assert dato_viejo not in worker._mensajes_procesados
        ack.assert_called_once()

    def test_datos_de_sesion_nueva_se_procesan(self, worker):
        ack = MagicMock()

        disconnect_msg = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "abc123"}'
        worker._callback_interno(INPUT_QUEUE_NAME, disconnect_msg, MagicMock(), MagicMock())

        dato_nuevo = b'{"client_id": "c1", "request_id": "c1:def456:q:1", "dato": 1}'
        worker._callback_interno(INPUT_QUEUE_NAME, dato_nuevo, ack, MagicMock())

        assert dato_nuevo in worker._mensajes_procesados

    def test_disconnect_sin_session_no_invalida_nada(self, worker):
        ack = MagicMock()

        disconnect_msg = b'{"client_id": "c1", "CLIENT_DISCONNECT": true}'
        worker._callback_interno(INPUT_QUEUE_NAME, disconnect_msg, MagicMock(), MagicMock())

        dato = b'{"client_id": "c1", "request_id": "c1:abc123:q:1", "dato": 1}'
        worker._callback_interno(INPUT_QUEUE_NAME, dato, ack, MagicMock())

        assert dato in worker._mensajes_procesados

    def test_datos_sin_request_id_no_se_filtran(self, worker):
        ack = MagicMock()

        disconnect_msg = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "abc123"}'
        worker._callback_interno(INPUT_QUEUE_NAME, disconnect_msg, MagicMock(), MagicMock())

        dato_sin_rid = b'{"client_id": "c1", "dato": 1}'
        worker._callback_interno(INPUT_QUEUE_NAME, dato_sin_rid, ack, MagicMock())

        assert dato_sin_rid in worker._mensajes_procesados

    def test_sesion_invalidada_se_limpia_al_completar_cliente(self, worker):
        worker._sesiones_invalidadas["c1"] = {"abc123"}
        worker.al_completar_cliente("c1")
        assert "c1" not in worker._sesiones_invalidadas

    def test_multiples_sesiones_invalidadas_acumulan(self, worker):
        d1 = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "s1"}'
        d2 = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "s2"}'
        worker._callback_interno(INPUT_QUEUE_NAME, d1, MagicMock(), MagicMock())
        worker._callback_interno(INPUT_QUEUE_NAME, d2, MagicMock(), MagicMock())

        dato_s1 = b'{"client_id": "c1", "request_id": "c1:s1:q:1"}'
        dato_s2 = b'{"client_id": "c1", "request_id": "c1:s2:q:1"}'
        dato_s3 = b'{"client_id": "c1", "request_id": "c1:s3:q:1"}'

        worker._callback_interno(INPUT_QUEUE_NAME, dato_s1, MagicMock(), MagicMock())
        worker._callback_interno(INPUT_QUEUE_NAME, dato_s2, MagicMock(), MagicMock())
        worker._callback_interno(INPUT_QUEUE_NAME, dato_s3, MagicMock(), MagicMock())

        assert dato_s1 not in worker._mensajes_procesados
        assert dato_s2 not in worker._mensajes_procesados
        assert dato_s3 in worker._mensajes_procesados

    def test_session_id_se_extrae_de_request_id_derivado(self, worker):
        disconnect_msg = b'{"client_id": "c1", "CLIENT_DISCONNECT": true, "session_id": "abc"}'
        worker._callback_interno(INPUT_QUEUE_NAME, disconnect_msg, MagicMock(), MagicMock())

        dato_derivado = b'{"client_id": "c1", "request_id": "c1:abc:q:1:s2:s1"}'
        ack = MagicMock()
        worker._callback_interno(INPUT_QUEUE_NAME, dato_derivado, ack, MagicMock())

        assert dato_derivado not in worker._mensajes_procesados
        ack.assert_called_once()
