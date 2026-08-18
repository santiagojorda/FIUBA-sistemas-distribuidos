"""
Tests para CounterWorker
========================
Cubren el conteo de mensajes simples y en batch, el flush al completar cliente
y el ciclo de vida básico.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


BASE_ENV = {
    "MOM_HOST": "rabbitmq",
    "NODE_PREFIX": "test_counter",
    "ID": "1",
    "TOTAL_WORKERS": "1",
    "INPUT_QUEUES": '["q_test_in"]',
    "OUTPUT_QUEUES": '["q_test_out"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
}


@pytest.fixture
def worker(tmp_path):
    with patch.dict("os.environ", BASE_ENV), \
         patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
         patch("common.middleware.FanoutQueueRabbitMQ"), \
         patch("common.middleware.FanoutExchangeRabbitMQ"), \
         patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)):
        from contador import CounterWorker
        w = CounterWorker()
    w._enviar = MagicMock()
    return w


def _msg(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


# ------------------------------------------------------------------
# Tests: conteo de mensajes
# ------------------------------------------------------------------

class TestContar:

    def test_mensaje_simple_incrementa_conteo(self, worker):
        payload = {"client_id": "c1", "request_id": "r1"}
        ack = MagicMock()

        worker.procesar_payload("q_in", "c1", payload, _msg(payload), ack, MagicMock())

        assert worker.estado._conteos["c1"] == 1
        ack.assert_called_once()

    def test_multiples_mensajes_acumulan_conteo(self, worker):
        for i in range(4):
            payload = {"client_id": "c1", "request_id": f"r{i}"}
            worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        assert worker.estado._conteos["c1"] == 4

    def test_batch_usa_count_del_header(self, worker):
        payload = {
            "client_id": "c1",
            "request_id": "r1",
            "batches": [{"header": {"count": 7, "schema": []}, "payload": []}],
        }

        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        assert worker.estado._conteos["c1"] == 7

    def test_multiples_batches_se_suman(self, worker):
        payload = {
            "client_id": "c1",
            "request_id": "r1",
            "batches": [
                {"header": {"count": 3, "schema": []}, "payload": []},
                {"header": {"count": 5, "schema": []}, "payload": []},
            ],
        }

        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        assert worker.estado._conteos["c1"] == 8

    def test_clientes_distintos_conteos_independientes(self, worker):
        for cid in ["c1", "c2"]:
            payload = {"client_id": cid, "request_id": f"r_{cid}"}
            worker.procesar_payload("q_in", cid, payload, _msg(payload), MagicMock(), MagicMock())

        assert worker.estado._conteos["c1"] == 1
        assert worker.estado._conteos["c2"] == 1

    def test_excepcion_llama_nack(self, worker):
        nack = MagicMock()
        ack = MagicMock()

        worker.procesar_payload("q_in", "c1", None, b"invalido", ack, nack)

        nack.assert_called_once()
        ack.assert_not_called()


# ------------------------------------------------------------------
# Tests: flush al completar cliente
# ------------------------------------------------------------------

class TestFlush:

    def test_al_completar_cliente_emite_el_conteo(self, worker):
        payload = {"client_id": "c1", "request_id": "r1"}
        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        worker.al_completar_cliente("c1")

        worker._enviar.assert_called_once()
        emitido = json.loads(worker._enviar.call_args[0][0])
        assert emitido["client_id"] == "c1"
        assert emitido["batches"][0]["payload"] == [[1]]

    def test_al_completar_cliente_emite_conteo_acumulado(self, worker):
        for i in range(5):
            payload = {"client_id": "c1", "request_id": f"r{i}"}
            worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        worker.al_completar_cliente("c1")

        emitido = json.loads(worker._enviar.call_args[0][0])
        assert emitido["batches"][0]["payload"] == [[5]]

    def test_al_completar_cliente_limpia_estado_interno(self, worker):
        payload = {"client_id": "c1", "request_id": "r1"}
        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        worker.al_completar_cliente("c1")

        assert "c1" not in worker.estado._conteos

    def test_schema_del_output_es_count(self, worker):
        payload = {"client_id": "c1", "request_id": "r1"}
        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        worker.al_completar_cliente("c1")

        emitido = json.loads(worker._enviar.call_args[0][0])
        assert emitido["batches"][0]["header"]["schema"] == ["count"]


# ------------------------------------------------------------------
# Tests: ciclo de vida
# ------------------------------------------------------------------

class TestCicloDeVida:

    def test_al_cerrar_no_falla(self, worker):
        worker.al_cerrar()

    def test_al_desconectar_cliente_limpia_estado(self, worker):
        payload = {"client_id": "c1", "request_id": "r1"}
        worker.procesar_payload("q_in", "c1", payload, _msg(payload), MagicMock(), MagicMock())

        worker.al_desconectar_cliente("c1")

        assert "c1" not in worker.estado._conteos


class TestToleranciaCaidasBug:

    def test_caida_despues_de_persistir_causa_duplicacion(self, tmp_path):
        import os
        from unittest.mock import patch, MagicMock
        import json
        from contador import CounterWorker

        payload = {"client_id": "c1", "request_id": "r_123"}
        msg_bytes = json.dumps(payload).encode("utf-8")

        # 1. Habilitamos el hook de crash después de persistir
        # y mockeamos os._exit para que en vez de matar el proceso del test lance una excepción simulación.
        env_con_crash = {
            **BASE_ENV,
            "CRASH_AFTER_PERSIST": "true",
        }

        class SimularCrashException(Exception):
            pass

        def simulacion_exit(code):
            raise SimularCrashException("El worker crasheó simuladamente antes del ack")

        # Inicializamos el primer worker
        with patch.dict("os.environ", env_con_crash), \
             patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
             patch("common.middleware.FanoutQueueRabbitMQ"), \
             patch("common.middleware.FanoutExchangeRabbitMQ"), \
             patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.crash_hook.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.dedup_filter.VOLUMEN_DIR", str(tmp_path)), \
             patch("os._exit", side_effect=simulacion_exit):
            
            w1 = CounterWorker()
            w1._enviar = MagicMock()
            
            # Procesamos el mensaje. Esto debe persistir el conteo en 1, 
            # y luego lanzar SimularCrashException al invocar el hook.
            ack_mock = MagicMock()
            nack_mock = MagicMock()
            
            # El callback interno del worker base maneja excepciones, 
            # pero la excepción del hook (si no la atrapa procesar_payload)
            # subirá. En contador.py:
            # try:
            #     cantidad = calcular_cantidad(payload)
            #     self.estado.incrementar(client_id, cantidad)
            #     if self._hook_post_persistir:
            #         self._hook_post_persistir()
            #     ack()
            # except Exception as e: ...
            # Como SimularCrashException es una Exception, contador.py la atrapará,
            # registrará el error y llamará a nack_mock().
            # Para estar seguros, verifiquemos si la excepción sube o es atrapada.
            # contador.py atrapa Exception general. Pero vamos a forzar/verificar.
            w1.procesar_payload("q_in", "c1", payload, msg_bytes, ack_mock, nack_mock)
            
            # El ack() no se llamó porque el hook disparó el exit (que atrapó contador, llamando a nack)
            ack_mock.assert_not_called()
            nack_mock.assert_called_once()
            
            # Verificamos que el estado en disco del contador sí se persistió
            assert w1.estado._conteos["c1"] == 1

        # 2. Ahora simulamos el reinicio del worker levantándolo de nuevo con el mismo volumen
        # El environment ya no tiene que crashear (o sí, pero para recibir la reentrega y procesar queremos que ande).
        # RabbitMQ reenviará el mensaje no ack-eado.
        with patch.dict("os.environ", BASE_ENV), \
             patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
             patch("common.middleware.FanoutQueueRabbitMQ"), \
             patch("common.middleware.FanoutExchangeRabbitMQ"), \
             patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.dedup_filter.VOLUMEN_DIR", str(tmp_path)):
            
            w2 = CounterWorker()
            w2._enviar = MagicMock()
            
            # El nuevo worker carga el estado persistido por w1 (que es 1)
            assert w2.estado._conteos["c1"] == 1
            
            # Sin embargo, el filtro de duplicados no guardó "r_123" porque no llegó a persistirse
            # (ya que el batch de persistencia del dedup no se llenó y no se hizo flush).
            # Por lo tanto, es_duplicado dará False.
            assert not w2.filtro_dedup.es_duplicado("c1", "r_123")
            
            # RabbitMQ nos reentrega el mensaje y lo procesamos nuevamente
            ack_mock2 = MagicMock()
            nack_mock2 = MagicMock()
            w2.procesar_payload("q_in", "c1", payload, msg_bytes, ack_mock2, nack_mock2)
            
            # Se procesó correctamente y se llamó a ack
            ack_mock2.assert_called_once()
            
            # ¡SOLUCIONADO! El contador ahora sigue siendo 1 porque se deduplicó el mensaje usando la persistencia atómica
            print(f"\n[DEMO BUG] Conteo final después del crash y reentrega: {w2.estado._conteos['c1']} (Esperado con fix: 1)")
            assert w2.estado._conteos["c1"] == 1


