"""Test de starvation del ACK del cliente.

Reproduce el bug donde los hilos de envío de datos monopolizan el
socket lock y el hilo receptor no puede enviar el ACK_RESULTADO
al gateway, causando un timeout y desconexión.
"""

import sys
import os
import types
import threading
import time
import unittest

raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if os.path.join(raiz, 'src/client') not in sys.path:
    sys.path.insert(0, os.path.join(raiz, 'src/client'))
    sys.path.insert(0, os.path.join(raiz, 'src'))

mock_config = types.ModuleType('config')
mock_config.OUTPUT_DIR = "output"
mock_config.SERVER_HOST = "127.0.0.1"
mock_config.SERVER_PORT = 5678
mock_config.TRANSACTIONS_FILE = "tx.csv"
mock_config.ACCOUNTS_FILE = "acc.csv"
mock_config.LOTE_SIZE = 5
sys.modules['config'] = mock_config

from unittest.mock import MagicMock, patch
from sender import _enviar_lotes
from receiver import _enviar_ack


def _mock_enviar(*args, **kwargs):
    pass


class TestAckStarvation(unittest.TestCase):

    def test_con_prioridad_ack_pasa_rapido(self):
        """Con el evento ack_pendiente, los senders ceden y el receptor
        adquiere el lock inmediatamente."""
        lock = threading.Lock()
        parar = threading.Event()
        ack_pendiente = threading.Event()
        ack_pendiente.set()
        ack_enviado = threading.Event()

        def sender_con_prioridad():
            while not parar.is_set():
                ack_pendiente.wait()
                with lock:
                    pass

        def receptor_con_prioridad():
            ack_pendiente.clear()
            with lock:
                ack_enviado.set()
            ack_pendiente.set()

        s1 = threading.Thread(target=sender_con_prioridad, daemon=True)
        s2 = threading.Thread(target=sender_con_prioridad, daemon=True)
        s1.start()
        s2.start()
        threading.Event().wait(timeout=0.05)

        inicio = time.monotonic()
        t = threading.Thread(target=receptor_con_prioridad, daemon=True)
        t.start()

        exito = ack_enviado.wait(timeout=1.0)
        duracion = time.monotonic() - inicio

        parar.set()
        ack_pendiente.set()
        s1.join(timeout=1)
        s2.join(timeout=1)

        self.assertTrue(exito, "El ACK no se envió a tiempo con prioridad")
        self.assertLess(duracion, 0.5, f"ACK tardó {duracion:.3f}s")

    def test_sender_cede_lock_cuando_ack_pendiente(self):
        """El sender real (_enviar_lotes) se pausa cuando ack_pendiente está clear."""
        lock = threading.Lock()
        ack_pendiente = threading.Event()
        ack_pendiente.set()

        envios = []

        def mock_enviar_con_registro(*a, **kw):
            envios.append(time.monotonic())

        registros = [["a", "b"]] * 20
        headers = ["col1", "col2"]
        sender_done = threading.Event()

        def run_sender():
            _enviar_lotes(headers, iter(registros), "LOTE", MagicMock(), lock,
                          "client1", ack_pendiente=ack_pendiente)
            sender_done.set()

        with patch('sender.message_protocol.external.enviar_mensaje', mock_enviar_con_registro):
            t = threading.Thread(target=run_sender, daemon=True)
            t.start()

            threading.Event().wait(timeout=0.05)

            ack_pendiente.clear()
            envios_al_pausar = len(envios)
            threading.Event().wait(timeout=0.1)
            envios_pausado = len(envios)

            self.assertEqual(envios_al_pausar, envios_pausado,
                             f"Sender envió {envios_pausado - envios_al_pausar} lotes "
                             f"mientras ack_pendiente estaba clear")

            ack_pendiente.set()
            sender_done.wait(timeout=5)

        self.assertTrue(sender_done.is_set(), "Sender no terminó tras liberar ack_pendiente")
        self.assertEqual(len(envios), 4)  # 20 registros / lote_size 5 = 4 lotes

    def test_receptor_envia_ack_mientras_sender_activo(self):
        """Test integrado: sender y receptor corren en paralelo,
        el receptor envía ACK sin starvation."""
        lock = threading.Lock()
        ack_pendiente = threading.Event()
        ack_pendiente.set()
        ack_completado = threading.Event()

        registros = [["x", "y"]] * 500
        headers = ["c1", "c2"]

        def run_sender():
            _enviar_lotes(headers, iter(registros), "LOTE", MagicMock(), lock,
                          "client1", ack_pendiente=ack_pendiente)

        def run_ack():
            threading.Event().wait(timeout=0.01)
            _enviar_ack(MagicMock(), "batch123", lock, ack_pendiente)
            ack_completado.set()

        with patch('sender.message_protocol.external.enviar_mensaje', _mock_enviar), \
             patch('receiver.message_protocol.external.enviar_mensaje', _mock_enviar):

            t_sender = threading.Thread(target=run_sender, daemon=True)
            t_ack = threading.Thread(target=run_ack, daemon=True)

            inicio = time.monotonic()
            t_sender.start()
            t_ack.start()

            exito = ack_completado.wait(timeout=5.0)
            duracion = time.monotonic() - inicio

            ack_pendiente.set()
            t_sender.join(timeout=2)
            t_ack.join(timeout=2)

        self.assertTrue(exito, "ACK no se completó — starvation")
        self.assertLess(duracion, 2.0, f"ACK tardó {duracion:.3f}s")

    def test_sin_ack_pendiente_sender_no_se_bloquea(self):
        """Sin ack_pendiente (None), el sender funciona normalmente."""
        lock = threading.Lock()
        envios = []

        def mock_enviar_con_registro(*a, **kw):
            envios.append(1)

        registros = [["a", "b"]] * 10
        headers = ["c1", "c2"]

        with patch('sender.message_protocol.external.enviar_mensaje', mock_enviar_con_registro):
            _enviar_lotes(headers, iter(registros), "LOTE", MagicMock(), lock,
                          "client1", ack_pendiente=None)

        self.assertEqual(len(envios), 2)  # 10 / 5 = 2 lotes

    def test_ack_pendiente_no_afecta_si_esta_set(self):
        """Con ack_pendiente siempre set, el sender no se pausa."""
        lock = threading.Lock()
        ack_pendiente = threading.Event()
        ack_pendiente.set()
        envios = []

        def mock_enviar_con_registro(*a, **kw):
            envios.append(1)

        registros = [["a", "b"]] * 15
        headers = ["c1", "c2"]

        with patch('sender.message_protocol.external.enviar_mensaje', mock_enviar_con_registro):
            _enviar_lotes(headers, iter(registros), "LOTE", MagicMock(), lock,
                          "client1", ack_pendiente=ack_pendiente)

        self.assertEqual(len(envios), 3)  # 15 / 5 = 3 lotes


if __name__ == "__main__":
    unittest.main()
