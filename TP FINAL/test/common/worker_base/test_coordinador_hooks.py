import threading
import time

import pytest
from unittest.mock import MagicMock, patch, call
from types import SimpleNamespace

from workers.base.coordinacion.coordinador import CoordinadorDistribuido
from workers.base.coordinacion.contador_vuelos import ContadorVuelos
from workers.base.coordinacion.hooks import HOOK_PRE_FINISHED
from common.constantes_protocolo import ID_CLIENTE
from base.constantes import (
    TIPO_MENSAJE,
    TIPO_EOF_RECIBIDO,
    TIPO_WORKER_FINALIZADO,
    TIPO_BARRERA_COMPLETA,
    ORIGINADOR,
    ID_WORKER,
)



def _crear_config(id_nodo=0, total_workers=2, sharded=True):
    return SimpleNamespace(
        id_nodo=id_nodo,
        total_workers=total_workers,
        prefijo_nodo="test",
        host_mom="localhost",
        colas_entrada=[f"cola_{id_nodo}"] if sharded else ["cola_comun"],
        tiene_cola_sharded=sharded,
    )


@pytest.fixture
def mocks_infra():
    with patch("workers.base.coordinacion.coordinador.PersistenciaCoordinacion") as mock_pers, \
         patch("workers.base.coordinacion.coordinador.TransporteControl") as mock_trans:
        mock_pers.return_value.cargar.return_value = ({}, [], [])
        mock_pers.return_value.guardar = MagicMock()
        mock_trans.return_value.enviar = MagicMock()
        yield {
            "persistencia": mock_pers.return_value,
            "transporte": mock_trans.return_value,
        }


def _crear_coordinador(mocks, hooks=None, id_nodo=0, total_workers=2, sharded=True):
    config = _crear_config(id_nodo, total_workers, sharded)
    coord = CoordinadorDistribuido(
        config,
        al_completar_sincronizacion=MagicMock(),
        al_completar_barrera=MagicMock(),
        contador_vuelos=ContadorVuelos(),
        hooks=hooks,
    )
    return coord


class TestEjecutarHook:

    def test_hook_registrado_se_ejecuta(self, mocks_infra):
        invocado = []
        coord = _crear_coordinador(mocks_infra, hooks={
            HOOK_PRE_FINISHED: lambda: invocado.append(True),
        })

        coord._ejecutar_hook(HOOK_PRE_FINISHED)

        assert invocado == [True]

    def test_hook_no_registrado_no_falla(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra, hooks={})

        coord._ejecutar_hook(HOOK_PRE_FINISHED)

    def test_sin_hooks_no_falla(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra)

        coord._ejecutar_hook(HOOK_PRE_FINISHED)

    def test_multiples_hooks_independientes(self, mocks_infra):
        registro = []
        coord = _crear_coordinador(mocks_infra, hooks={
            HOOK_PRE_FINISHED: lambda: registro.append(HOOK_PRE_FINISHED),
            "post_barrera": lambda: registro.append("post_barrera"),
        })

        coord._ejecutar_hook(HOOK_PRE_FINISHED)
        coord._ejecutar_hook("post_barrera")

        assert registro == [HOOK_PRE_FINISHED, "post_barrera"]


class TestHookPreFinished:

    def test_hook_pre_finished_se_ejecuta_durante_flush(self, mocks_infra):
        invocado = []
        coord = _crear_coordinador(mocks_infra, hooks={
            HOOK_PRE_FINISHED: lambda: invocado.append(True),
        })

        coord._ejecutar_flush_y_notificar("c1", 0)

        assert invocado == [True]

    def test_hook_pre_finished_se_ejecuta_antes_de_enviar_worker_finalizado(self, mocks_infra):
        orden = []
        transporte = mocks_infra["transporte"]
        transporte.enviar.side_effect = lambda msg: orden.append("envio")

        coord = _crear_coordinador(mocks_infra, hooks={
            HOOK_PRE_FINISHED: lambda: orden.append("hook"),
        })

        coord._ejecutar_flush_y_notificar("c1", 0)

        assert orden.index("hook") < orden.index("envio")

    def test_hook_que_lanza_excepcion_impide_envio_finished(self, mocks_infra):
        def hook_crash():
            raise RuntimeError("crash simulado")

        coord = _crear_coordinador(mocks_infra, hooks={
            HOOK_PRE_FINISHED: hook_crash,
        })

        with pytest.raises(RuntimeError, match="crash simulado"):
            coord._ejecutar_flush_y_notificar("c1", 0)

        mocks_infra["transporte"].enviar.assert_not_called()

    def test_flush_sin_hooks_envia_worker_finalizado(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra)

        coord._ejecutar_flush_y_notificar("c1", 0)

        mocks_infra["transporte"].enviar.assert_called_once()
        msg = mocks_infra["transporte"].enviar.call_args[0][0]
        assert msg[TIPO_MENSAJE] == TIPO_WORKER_FINALIZADO

    def test_flush_llama_al_completar_sincronizacion(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra)

        coord._ejecutar_flush_y_notificar("c1", 0)

        coord._al_completar_sincronizacion.assert_called_once_with("c1", None)

    def test_flush_ya_realizado_no_llama_sincronizacion_de_nuevo(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra)

        coord._ejecutar_flush_y_notificar("c1", 0)
        coord._al_completar_sincronizacion.reset_mock()

        coord._ejecutar_flush_y_notificar("c1", 0)

        coord._al_completar_sincronizacion.assert_not_called()


class TestBarreraConHooks:

    def test_iniciar_barrera_difunde_eof_recibido(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra, id_nodo=0)

        coord.iniciar_barrera("c1", b"msg_original")

        mocks_infra["transporte"].enviar.assert_called_once()
        msg = mocks_infra["transporte"].enviar.call_args[0][0]
        assert msg[TIPO_MENSAJE] == TIPO_EOF_RECIBIDO
        assert msg[ORIGINADOR] == 0

    def test_barrera_completa_con_todos_los_workers(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra, id_nodo=0, total_workers=2)

        coord.iniciar_barrera("c1", b"msg_original")
        mocks_infra["transporte"].enviar.reset_mock()

        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 0, ID_WORKER: 0,
        })
        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 0, ID_WORKER: 1,
        })

        msgs_enviados = [c[0][0] for c in mocks_infra["transporte"].enviar.call_args_list]
        tipos = [m[TIPO_MENSAJE] for m in msgs_enviados]
        assert TIPO_BARRERA_COMPLETA in tipos

    def test_worker_finalizado_de_otro_originador_se_ignora(self, mocks_infra):
        coord = _crear_coordinador(mocks_infra, id_nodo=0)

        coord.iniciar_barrera("c1", b"msg_original")
        mocks_infra["transporte"].enviar.reset_mock()

        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 99, ID_WORKER: 1,
        })

        mocks_infra["transporte"].enviar.assert_not_called()


class TestFlushAsyncNoDeadlock:
    """Verifica que el flush async no deadlockea cuando hay mensajes en vuelo.

    Escenario real: el hilo de datos recibe un EOF y llama iniciar_barrera.
    Si hay mensajes en vuelo (counter > 0), esperar_cero bloquea.
    Antes del fix, esto bloqueaba el mismo hilo que necesitaba ackear
    los mensajes para descontar el counter → deadlock.
    Con el fix (flush en hilo separado), el hilo de datos retorna
    inmediatamente y puede seguir ackeando.
    """

    def test_flush_no_bloquea_hilo_que_llama_iniciar_barrera(self, mocks_infra):
        contador = ContadorVuelos()
        config = _crear_config(id_nodo=0, total_workers=1, sharded=True)
        coord = CoordinadorDistribuido(
            config,
            al_completar_sincronizacion=MagicMock(),
            al_completar_barrera=MagicMock(),
            contador_vuelos=contador,
        )

        contador.registrar("c1")

        # Simular que otro worker ya difundió EOF_RECEIVED (seteamos originador)
        with coord._coordinacion_lock:
            ec = coord._obtener("c1")
            ec.originador = 0

        hilo_retorno = threading.Event()

        def llamar_barrera():
            coord.iniciar_barrera("c1", b"msg")
            hilo_retorno.set()

        t = threading.Thread(target=llamar_barrera)
        t.start()

        # iniciar_barrera debe retornar inmediatamente (flush en otro hilo)
        assert hilo_retorno.wait(timeout=2), \
            "iniciar_barrera bloqueó el hilo llamador — deadlock"

        # El flush está esperando vuelos a cero en background
        coord._al_completar_sincronizacion.assert_not_called()

        # Simular que el hilo de datos ackea el mensaje pendiente
        contador.descontar("c1")

        # El flush async debe completar
        time.sleep(0.2)
        coord._al_completar_sincronizacion.assert_called_once_with("c1", None)
        t.join(timeout=1)

    def test_flush_async_completa_cuando_vuelos_llegan_a_cero(self, mocks_infra):
        contador = ContadorVuelos()
        config = _crear_config(id_nodo=0, total_workers=1, sharded=True)
        flush_completado = threading.Event()
        sincronizacion_original = MagicMock(side_effect=lambda *a: flush_completado.set())

        coord = CoordinadorDistribuido(
            config,
            al_completar_sincronizacion=sincronizacion_original,
            al_completar_barrera=MagicMock(),
            contador_vuelos=contador,
        )

        # 3 mensajes en vuelo
        for _ in range(3):
            contador.registrar("c1")

        with coord._coordinacion_lock:
            ec = coord._obtener("c1")
            ec.originador = 0

        coord.iniciar_barrera("c1", b"msg")

        # Flush no debería haber corrido aún
        assert not flush_completado.is_set()

        # Descontar de a uno
        contador.descontar("c1")
        time.sleep(0.05)
        assert not flush_completado.is_set()

        contador.descontar("c1")
        time.sleep(0.05)
        assert not flush_completado.is_set()

        # Último descuento libera el flush
        contador.descontar("c1")
        assert flush_completado.wait(timeout=2), \
            "El flush async no completó tras descontar todos los vuelos"

    def test_manejar_eof_recibido_no_bloquea_con_vuelos_pendientes(self, mocks_infra):
        contador = ContadorVuelos()
        config = _crear_config(id_nodo=0, total_workers=1, sharded=True)
        coord = CoordinadorDistribuido(
            config,
            al_completar_sincronizacion=MagicMock(),
            al_completar_barrera=MagicMock(),
            contador_vuelos=contador,
        )

        contador.registrar("c1")

        # Marcar EOF local como completo y setear originador
        with coord._coordinacion_lock:
            ec = coord._obtener("c1")
            ec.eof_local_completo = True
            ec.originador = 0
            ec.barrera_activa = True

        hilo_retorno = threading.Event()

        def llamar_eof_recibido():
            coord._manejar_eof_recibido({
                ID_CLIENTE: "c1",
                ORIGINADOR: 0,
            })
            hilo_retorno.set()

        t = threading.Thread(target=llamar_eof_recibido)
        t.start()

        assert hilo_retorno.wait(timeout=2), \
            "_manejar_eof_recibido bloqueó el hilo — deadlock"

        # Liberar vuelos para que el flush async complete
        contador.descontar("c1")
        time.sleep(0.2)
        coord._al_completar_sincronizacion.assert_called_once()
        t.join(timeout=1)
