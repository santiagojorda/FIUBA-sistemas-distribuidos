"""
Test de tolerancia a fallos: Condición de carrera de EOF y mensajes rezagados
=============================================================================
Este test valida que si un worker recibe un EOF prematuro mientras un mensaje de datos
todavía no ha sido procesado (por ejemplo, debido a una caída/crash y posterior reentrega),
el worker NO debe cerrar la barrera ni limpiar su estado hasta que todos los mensajes
esperados (total_mensajes_enviados) hayan sido procesados.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
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


def _msg(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


class LoopbackTransporteControl:
    def __init__(self, config):
        self.callback = None
    def enviar(self, msg_dict):
        if self.callback:
            from common.message_protocol.internal import ParseadorMensajes
            mensaje_bytes = ParseadorMensajes.serializar(msg_dict)
            import threading
            threading.Thread(
                target=self.callback,
                args=(mensaje_bytes, MagicMock(), MagicMock()),
                daemon=True
            ).start()
    def iniciar_consumo(self, callback):
        self.callback = callback
    def detener_consumo(self):
        pass
    def cerrar(self):
        pass


class TestEOFRaceCondition:

    def test_eof_race_condition_no_completa_barrera_si_faltan_mensajes(self, tmp_path):
        client_id = "client_1"
        
        # Payload de los mensajes de datos
        payload_r1 = {"client_id": client_id, "request_id": "r1"}
        payload_r2 = {"client_id": client_id, "request_id": "r2"}
        payload_r3 = {"client_id": client_id, "request_id": "r3"}  # El mensaje rezagado (X)

        # Payload de EOF indicando que se enviaron 3 mensajes en total
        payload_eof = {
            "client_id": client_id,
            "EOF": True,
            "total_mensajes_enviados": 3
        }

        # 1. Instanciamos el primer worker y procesamos los dos primeros mensajes
        import common.persistencia
        original_init = common.persistencia.PersistidorEstado.__init__

        def patched_init(self, node_name, base_dir=None):
            if base_dir is None or base_dir == "/app/volumen":
                base_dir = str(tmp_path)
            original_init(self, node_name, base_dir)

        with patch.dict("os.environ", BASE_ENV), \
             patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
             patch("common.middleware.FanoutQueueRabbitMQ"), \
             patch("common.middleware.FanoutExchangeRabbitMQ"), \
             patch("base.coordinacion.coordinador.TransporteControl", LoopbackTransporteControl), \
             patch.object(common.persistencia.PersistidorEstado, "__init__", patched_init), \
             patch("common.persistencia.VOLUMEN_DIR", str(tmp_path)), \
             patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.crash_hook.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.dedup_filter.VOLUMEN_DIR", str(tmp_path)):

            from contador import CounterWorker
            w1 = CounterWorker()
            w1.coordinador.iniciar_consumo()
            w1._enviar = MagicMock()

            # Procesamos r1 y r2
            w1.procesar_payload("q_test_in", client_id, payload_r1, _msg(payload_r1), MagicMock(), MagicMock())
            w1.procesar_payload("q_test_in", client_id, payload_r2, _msg(payload_r2), MagicMock(), MagicMock())

            assert len(w1.estado._ids_procesados.get(client_id, set())) == 2

            # 2. Simulamos que al llegar r3, el worker se cae (crashea) antes de procesarlo.
            # No llamamos a procesar_payload para r3 en w1, simulando que volvió a la cola de RabbitMQ.
            # Guardamos el estado persistido hasta ahora.

        # 3. Levantamos un segundo worker w2 (reinicio/recovery del worker caído)
        with patch.dict("os.environ", BASE_ENV), \
             patch("common.middleware.MessageMiddlewareQueueRabbitMQ"), \
             patch("common.middleware.FanoutQueueRabbitMQ"), \
             patch("common.middleware.FanoutExchangeRabbitMQ"), \
             patch("base.coordinacion.coordinador.TransporteControl", LoopbackTransporteControl), \
             patch.object(common.persistencia.PersistidorEstado, "__init__", patched_init), \
             patch("common.persistencia.VOLUMEN_DIR", str(tmp_path)), \
             patch("persistencia_conteo.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.crash_hook.VOLUMEN_DIR", str(tmp_path)), \
             patch("common.dedup_filter.VOLUMEN_DIR", str(tmp_path)):

            w2 = CounterWorker()
            w2.coordinador.iniciar_consumo()
            w2._enviar = MagicMock()

            # Verificamos que recuperó el estado procesado de w1 (2 mensajes procesados)
            assert len(w2.estado._ids_procesados.get(client_id, set())) == 2

            # 4. RabbitMQ entrega el mensaje EOF antes del mensaje rezagado r3 (condición de carrera)
            ack_eof = MagicMock()
            w2._callback_interno("q_test_in", _msg(payload_eof), ack_eof, MagicMock())

            # 5. VERIFICACIÓN CRÍTICA:
            # Como len(_ids_procesados) = 2 y total_mensajes_enviados = 3,
            # el worker NO debe haber cerrado la barrera, ni haber enviado el EOF al downstream,
            # ni haber limpiado su estado.
            w2._enviar.assert_not_called()

            # El estado del cliente debe seguir existiendo en el worker
            assert client_id in w2.estado._conteos
            assert len(w2.estado._ids_procesados.get(client_id, set())) == 2

            # 6. Finalmente, RabbitMQ reentrega el mensaje rezagado r3 y se procesa
            ack_r3 = MagicMock()
            w2._callback_interno("q_test_in", _msg(payload_r3), ack_r3, MagicMock())

            # Esperamos a que el procesamiento asíncrono del loopback termine
            import time
            time.sleep(0.1)

            # 7. Con todos los mensajes procesados, la barrera/EOF debería poder completarse.
            # Verificamos que se haya enviado el resultado (barrera resuelta)
            w2._enviar.assert_called_once()
            
            # Verificamos que se limpie el estado al finalizar
            assert client_id not in w2.estado._conteos
