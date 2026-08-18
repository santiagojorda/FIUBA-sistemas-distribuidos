import sys
import os
import types
import importlib.util

raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
while raiz in sys.path:
    sys.path.remove(raiz)
sys.path.insert(0, os.path.join(raiz, 'src/gateway'))
sys.path.insert(0, os.path.join(raiz, 'src/client'))
sys.path.insert(0, os.path.join(raiz, 'src'))

# Crear modulo config sintetico unificado para evitar colision en sys.modules
mock_config = types.ModuleType('config')
mock_config.OUTPUT_DIR = "output"
mock_config.SERVER_HOST = "127.0.0.1"
mock_config.SERVER_PORT = 5678
mock_config.TRANSACTIONS_FILE = "tx.csv"
mock_config.ACCOUNTS_FILE = "acc.csv"
mock_config.LOTE_SIZE = 1000

# Cargar GatewayConfig real
spec = importlib.util.spec_from_file_location("gateway_config", os.path.join(raiz, "src/gateway/config.py"))
gateway_config_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway_config_mod)
mock_config.GatewayConfig = gateway_config_mod.GatewayConfig

sys.modules['config'] = mock_config

import json
import pytest
from unittest.mock import MagicMock, patch
from gateway.client_handler import ClientHandler
from gateway.backend import BackendListener
from common.constantes_protocolo import CABECERA, ESQUEMA, PAYLOAD, ID_CLIENTE, ID_SOLICITUD, LOTES, CLAVE_QUERY, CLAVE_RESULTADO, CLAVE_EOF_REPORTE
from config import GatewayConfig
from common.crash_hook import CrashHook
from common import crash_points as CP

class DummyConfig:
    def __init__(self):
        self.mom_host = "localhost"
        self.input_queues = ["q1_pre_projection"]
        self.num_queries = 1
        self.eofs_esperados = {"q1_pre_projection": 1}
        self.bank_queue_config = {"total_workers": 1, "hash_field": "Bank ID"}
        self.DEFAULT_WORKERS = 1

class DummyState:
    def __init__(self):
        self.clientes = {}
        self.servidor_corriendo = True
        self.estados_persistidos = {}

    def registrar_cliente(self, client_id, sock):
        self.clientes[client_id] = (sock, None, set())

    def obtener_cliente(self, client_id):
        return self.clientes.get(client_id, (None, None, None))

    def remover_cliente(self, client_id):
        self.clientes.pop(client_id, None)

    def cargar_estado_cliente(self, client_id):
        return self.estados_persistidos.setdefault(client_id, {"queries_entregadas": [], "datos_enviados": False})

    def guardar_estado_cliente(self, client_id, estado):
        self.estados_persistidos[client_id] = estado

    def limpiar_estado_cliente(self, client_id):
        self.estados_persistidos.pop(client_id, None)

    def registrar_ack_esperado(self, client_id, batch_id):
        evt = MagicMock()
        return evt

    def notificar_ack(self, client_id, batch_id):
        pass

    def generar_request_id(self, client_id, queue_name):
        return f"{client_id}_{queue_name}_1"

# --- Tests ---

def test_client_id_from_env(tmp_path):
    """Verifica que el cliente priorice la variable de entorno CLIENT_ID."""
    import client.client as client_mod
    env = {"CLIENT_ID": "test-env-id-123", "OUTPUT_DIR": str(tmp_path)}
    with patch.dict("os.environ", env):
        cid = client_mod._cargar_o_generar_client_id()
        assert cid == "test-env-id-123"

def test_gateway_upstream_crash_hook(tmp_path):
    """Verifica que el gateway lance os._exit ante el hook de upstream."""
    config = DummyConfig()
    state = DummyState()
    handler = ClientHandler(config, state)

    # Preparar el archivo bandera y volumen
    env = {
        "CRASH_GATEWAY_UPSTREAM_BEFORE_ACK": "true",
    }
    
    with patch.dict("os.environ", env), \
         patch("common.persistencia.VOLUMEN_DIR", str(tmp_path)), \
         patch("os._exit") as mock_exit:
         
        handler._hook = CrashHook(volumen_dir=str(tmp_path))
        handler._hook.verificar(CP.GW_UPSTREAM_BEFORE_ACK, "upstream client-1")
        
        # Debe haber llamado a os._exit(1)
        mock_exit.assert_called_once_with(1)
        
        # El archivo de bandera debe haberse creado
        bandera = tmp_path / "crash_CRASH_GATEWAY_UPSTREAM_BEFORE_ACK_done"
        assert bandera.exists()

def test_gateway_downstream_crash_hook(tmp_path):
    """Verifica que el gateway lance os._exit ante el hook de downstream."""
    config = DummyConfig()
    state = DummyState()
    listener = BackendListener(config, state)

    env = {
        "CRASH_GATEWAY_DOWNSTREAM_BEFORE_SEND": "true",
    }
    
    with patch.dict("os.environ", env), \
         patch("common.persistencia.VOLUMEN_DIR", str(tmp_path)), \
         patch("os._exit") as mock_exit:
         
        listener._hook = CrashHook(volumen_dir=str(tmp_path))
        listener._hook.verificar(CP.GW_DOWNSTREAM_BEFORE_SEND, "before-send-eof client-1")
        
        mock_exit.assert_called_once_with(1)
        bandera = tmp_path / "crash_CRASH_GATEWAY_DOWNSTREAM_BEFORE_SEND_done"
        assert bandera.exists()
