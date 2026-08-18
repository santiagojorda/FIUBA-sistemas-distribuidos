import pytest
from unittest.mock import MagicMock, patch
import json
import time
import common.persistencia
from base.constantes import TIPO_WORKER_FINALIZADO, ID_WORKER
from common.message_protocol.internal import ParseadorMensajes
from base.coordinacion.coordinador import CoordinadorDistribuido
from base.coordinacion.estado_cliente import EstadoClienteCoordinacion
from base.coordinacion.manejador_eof import ManejadorCoordinacionEof
from base.coordinacion.mensajes_control import msg_worker_finalizado

BASE_ENV = {
    "MOM_HOST": "localhost",
    "NODE_PREFIX": "contador",
    "ID": "1",
    "TOTAL_WORKERS": "2",
    "INPUT_QUEUES": '["q_in"]',
    "OUTPUT_QUEUES": '["q_out"]',
    "HEARTBEAT_INTERVAL_SECONDS": "0",
}

class LoopbackTransporteControl:
    def __init__(self, config):
        self.callback = None
        self.cola = MagicMock()
        self.exchange = MagicMock()

    def enviar(self, msg_dict):
        if self.callback:
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

def _msg(payload):
    return json.dumps(payload).encode("utf-8")

class TestBarreraConCaidas:

    def test_barrera_distribuida_valida_e_integra_conteos_con_caidas(self, tmp_path):
        client_id = "client_1"
        payload_eof_upstream_w1 = {
            "client_id": client_id,
            "EOF": True,
            "total_mensajes_enviados": 2
        }
        payload_eof_upstream_w2 = {
            "client_id": client_id,
            "EOF": True,
            "total_mensajes_enviados": 2
        }

        # Redirigir persistencia temporalmente
        original_init = common.persistencia.PersistidorEstado.__init__
        def patched_init(self, node_name, base_dir=None):
            if base_dir is None or base_dir == "/app/volumen":
                base_dir = str(tmp_path)
            original_init(self, node_name, base_dir)

        # Configuración simulada de entorno
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
            
            # Instanciar Shard 1 (Originador de la barrera)
            with patch.dict("os.environ", {"ID": "1"}):
                w1 = CounterWorker()
                w1.enrutador.enviar = MagicMock()
                w1.coordinador.iniciar_consumo()
            
            # Procesar mensajes de datos localmente en Shard 1 (2 procesados, 2 emitidos)
            w1._mensajes_procesados[client_id] = 2
            w1._mensajes_emitidos[client_id] = 2
            w1._persistir_conteos()

            # Shard 1 recibe el EOF upstream
            w1._callback_interno("q_in", _msg(payload_eof_upstream_w1), MagicMock(), MagicMock())

            # Esperar a que el loopback entregue el mensaje de control asíncronamente
            time.sleep(0.1)

            # Shard 1 (como originador de la barrera) habrá iniciado la barrera (confirmados: 1/2)
            ec1 = w1.coordinador._clientes[client_id]
            assert ec1.barrera_activa is True
            assert len(ec1.workers_confirmados) == 1  # Solo w1 se ha confirmado a sí mismo
            assert 1 in ec1.workers_confirmados or "1" in ec1.workers_confirmados
            assert ec1.worker_conteos.get("1") == {"procesados": 2, "emitidos": 2} or ec1.worker_conteos.get(1) == {"procesados": 2, "emitidos": 2}

            # La barrera todavía no se completa ni se envía el EOF downstream (se permite la llamada del flush local)
            for call_args in w1.enrutador.enviar.call_args_list:
                payload_sent = ParseadorMensajes.deserializar(call_args[0][0])
                assert "EOF" not in payload_sent

            # Instanciar Shard 2
            with patch.dict("os.environ", {"ID": "2"}):
                w2 = CounterWorker()
                w2.enrutador.enviar = MagicMock()
                w2.coordinador.iniciar_consumo()

            # Simular procesamiento en Shard 2 (2 procesados, 1 emitido - filtro descarta uno)
            w2._mensajes_procesados[client_id] = 2
            w2._mensajes_emitidos[client_id] = 1
            w2._persistir_conteos()

            # Shard 2 recibe el EOF
            w2._callback_interno("q_in", _msg(payload_eof_upstream_w2), MagicMock(), MagicMock())

            # Esperar a que w2 mande su msg_worker_finalizado al originador w1
            time.sleep(0.1)

            # Simular que el mensaje de control de Shard 2 llega al originador Shard 1
            control_msg_w2 = msg_worker_finalizado(
                client_id, originador=1, id_nodo=2,
                mensajes_procesados=2, mensajes_emitidos=1
            )
            w1.coordinador._manejar_worker_finalizado(control_msg_w2)

            # La barrera distribuida en w1 debe haberse completado (2/2 confirmados)
            assert ec1.barrera_activa is False

            # Verificación del EOF mutado downstream
            # Se esperan 2 llamadas: la del flush local de w1 y la del EOF consolidado final
            assert w1.enrutador.enviar.call_count == 2
            
            # Buscar la llamada correspondiente al EOF
            eof_call_arg = None
            for call_args in w1.enrutador.enviar.call_args_list:
                payload_sent = ParseadorMensajes.deserializar(call_args[0][0])
                if "EOF" in payload_sent:
                    eof_call_arg = payload_sent
                    break
            
            assert eof_call_arg is not None
            # El total consolidado de mensajes emitidos downstream es 2 (w1) + 1 (w2) = 3
            assert eof_call_arg["total_mensajes_enviados"] == 3
            # El request_id del EOF downstream debe ser incremental y contener el ID del nodo
            assert eof_call_arg["request_id"] == f"{client_id}:eof:1:4"
