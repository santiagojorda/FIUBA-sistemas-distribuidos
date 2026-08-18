"""
Tests de recovery del coordinador distribuido
==============================================
Cubren:
  - Caso 5: coordinator recibe WORKER_FINISHED tardío tras recovery
  - Caso 6: coordinator reenvía WORKER_FINISHED tras recovery (flush completado)
  - Recovery de barrera completa pendiente de difusión
"""
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from workers.base.coordinacion.coordinador import CoordinadorDistribuido
from workers.base.coordinacion.persistencia import PersistenciaCoordinacion
from workers.base.coordinacion.estado_cliente import EstadoClienteCoordinacion
from workers.base.coordinacion.contador_vuelos import ContadorVuelos
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


def _crear_coordinador_con_persistencia(tmp_path, id_nodo=0, total_workers=2,
                                         al_completar_sincronizacion=None,
                                         al_completar_barrera=None,
                                         hooks=None):
    config = _crear_config(id_nodo, total_workers)
    with patch("workers.base.coordinacion.coordinador.TransporteControl") as mock_trans, \
         patch("workers.base.coordinacion.persistencia.PersistidorEstado") as mock_pe:
        mock_pe.return_value.directory = str(tmp_path / f"coordinator_test_{id_nodo}")
        mock_pe.return_value.guardar = MagicMock()
        mock_pe.return_value.cargar = MagicMock(return_value={})
        mock_trans.return_value.enviar = MagicMock()

        coord = CoordinadorDistribuido(
            config,
            al_completar_sincronizacion=al_completar_sincronizacion or MagicMock(),
            al_completar_barrera=al_completar_barrera or MagicMock(),
            contador_vuelos=ContadorVuelos(),
            hooks=hooks,
        )
        return coord, mock_trans.return_value


def _escribir_estado_coordinador(tmp_path, id_nodo, estado):
    from common.persistencia import PersistidorEstado
    p = PersistidorEstado(f"coordinator_test_{id_nodo}", base_dir=str(tmp_path))
    p.guardar(estado)


def _crear_coordinador_con_recovery(tmp_path, id_nodo=0, total_workers=2,
                                     al_completar_sincronizacion=None,
                                     al_completar_barrera=None):
    config = _crear_config(id_nodo, total_workers)
    with patch("workers.base.coordinacion.coordinador.TransporteControl") as mock_trans, \
         patch("workers.base.coordinacion.persistencia.PersistidorEstado") as mock_pe:
        from common.persistencia import PersistidorEstado
        real_pe = PersistidorEstado(f"coordinator_test_{id_nodo}", base_dir=str(tmp_path))
        mock_pe.return_value.directory = real_pe.directory
        mock_pe.return_value.guardar = real_pe.guardar
        mock_pe.return_value.cargar = real_pe.cargar
        mock_trans.return_value.enviar = MagicMock()

        coord = CoordinadorDistribuido(
            config,
            al_completar_sincronizacion=al_completar_sincronizacion or MagicMock(),
            al_completar_barrera=al_completar_barrera or MagicMock(),
            contador_vuelos=ContadorVuelos(),
        )
        return coord, mock_trans.return_value


# ──────────────────────────────────────────────────────────────────
# Caso 5 — Coordinator recibe WORKER_FINISHED tardío tras recovery
#   El coordinator muere después de completar la barrera.
#   Al reiniciar, recuerda clientes_finalizados y responde
#   correctamente a mensajes WORKER_FINISHED tardíos.
# ──────────────────────────────────────────────────────────────────

class TestCaso5ClienteFinalizadoRecovery:

    def test_cliente_finalizado_se_recupera_desde_disco(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": ["c1"],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)

        assert "c1" in coord._clientes
        assert coord._clientes["c1"].finalizado is True

    def test_worker_finished_tardio_se_ignora_silenciosamente(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": ["c1"],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)

        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 0, ID_WORKER: 1,
        })

        transporte.enviar.assert_not_called()

    def test_worker_finished_tardio_de_otro_originador_se_ignora(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": ["c1"],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)

        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 99, ID_WORKER: 1,
        })

        transporte.enviar.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# Caso 6 — Coordinator reenvía WORKER_FINISHED tras recovery
#   El worker hizo el flush pero murió antes de confirmar
#   WORKER_FINISHED. Al reiniciar, detecta flush_completados
#   y reenvía la confirmación.
# ──────────────────────────────────────────────────────────────────

class TestCaso6FlushCompletadoRecovery:

    def test_flush_completado_se_recupera_desde_disco(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {"c1": 2},
            "clientes_finalizados": [],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)

        ec = coord._clientes["c1"]
        assert ec.flusheado is True
        assert ec.originador_flush == 2

    def test_procesar_barreras_recuperadas_reenvia_worker_finished(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {"c1": 2},
            "clientes_finalizados": [],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)
        coord.procesar_barreras_recuperadas()

        transporte.enviar.assert_called_once()
        msg = transporte.enviar.call_args[0][0]
        assert msg[TIPO_MENSAJE] == TIPO_WORKER_FINALIZADO
        assert msg[ID_CLIENTE] == "c1"
        assert msg[ORIGINADOR] == 2
        assert msg[ID_WORKER] == 0

    def test_multiples_flush_pendientes_se_reenvian_todos(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {},
            "eofs_locales_recibidos": {},
            "flush_completados": {"c1": 2, "c2": 3},
            "clientes_finalizados": [],
        })

        coord, transporte = _crear_coordinador_con_recovery(tmp_path, id_nodo=0)
        coord.procesar_barreras_recuperadas()

        assert transporte.enviar.call_count == 2
        clientes_enviados = {
            c[0][0][ID_CLIENTE] for c in transporte.enviar.call_args_list
        }
        assert clientes_enviados == {"c1", "c2"}


# ──────────────────────────────────────────────────────────────────
# Recovery de barrera completa pendiente de difusión
#   Todos los workers confirmaron pero el coordinator murió
#   antes de difundir BARRERA_COMPLETA. Al reiniciar,
#   procesar_barreras_recuperadas lo completa.
# ──────────────────────────────────────────────────────────────────

class TestBarreraCompletaRecovery:

    def test_barrera_con_todos_confirmados_se_completa_en_recovery(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {
                "c1": {
                    "workers_confirmados": [0, 1],
                    "mensaje_payload": {"client_id": "c1", "data": "test"},
                }
            },
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": [],
        })

        al_completar = MagicMock()
        coord, transporte = _crear_coordinador_con_recovery(
            tmp_path, id_nodo=0, total_workers=2,
            al_completar_sincronizacion=al_completar,
        )
        coord.procesar_barreras_recuperadas()

        transporte.enviar.assert_called_once()
        msg = transporte.enviar.call_args[0][0]
        assert msg[TIPO_MENSAJE] == TIPO_BARRERA_COMPLETA
        assert msg[ID_CLIENTE] == "c1"
        al_completar.assert_called_once()

    def test_barrera_parcial_no_se_completa_en_recovery(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {
                "c1": {
                    "workers_confirmados": [0],
                    "mensaje_payload": None,
                }
            },
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": [],
        })

        al_completar = MagicMock()
        coord, transporte = _crear_coordinador_con_recovery(
            tmp_path, id_nodo=0, total_workers=2,
            al_completar_sincronizacion=al_completar,
        )
        coord.procesar_barreras_recuperadas()

        transporte.enviar.assert_not_called()
        al_completar.assert_not_called()

    def test_barrera_parcial_se_completa_con_worker_faltante(self, tmp_path):
        _escribir_estado_coordinador(tmp_path, 0, {
            "coordinaciones_eof": {
                "c1": {
                    "workers_confirmados": [0],
                    "mensaje_payload": None,
                }
            },
            "eofs_locales_recibidos": {},
            "flush_completados": {},
            "clientes_finalizados": [],
        })

        al_completar = MagicMock()
        coord, transporte = _crear_coordinador_con_recovery(
            tmp_path, id_nodo=0, total_workers=2,
            al_completar_sincronizacion=al_completar,
        )
        coord.procesar_barreras_recuperadas()

        transporte.enviar.assert_not_called()

        coord._manejar_worker_finalizado({
            ID_CLIENTE: "c1", ORIGINADOR: 0, ID_WORKER: 1,
        })

        msgs = [c[0][0] for c in transporte.enviar.call_args_list]
        tipos = [m[TIPO_MENSAJE] for m in msgs]
        assert TIPO_BARRERA_COMPLETA in tipos
        al_completar.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# Crash con hook + recovery end-to-end
#   Simula: coordinador arranca, inicia barrera, flush crashea
#   via hook, segundo coordinador recupera y completa.
# ──────────────────────────────────────────────────────────────────

class TestCrashYRecoveryEndToEnd:

    def test_crash_pre_finished_y_recovery_completa_barrera(self, tmp_path):
        config = _crear_config(id_nodo=0, total_workers=1)

        with patch("workers.base.coordinacion.coordinador.TransporteControl") as mock_trans, \
             patch("workers.base.coordinacion.persistencia.PersistidorEstado") as mock_pe:
            from common.persistencia import PersistidorEstado
            real_pe = PersistidorEstado("coordinator_test_0", base_dir=str(tmp_path))
            mock_pe.return_value.directory = real_pe.directory
            mock_pe.return_value.guardar = real_pe.guardar
            mock_pe.return_value.cargar = real_pe.cargar
            mock_trans.return_value.enviar = MagicMock()

            coord1 = CoordinadorDistribuido(
                config,
                al_completar_sincronizacion=MagicMock(),
                al_completar_barrera=MagicMock(),
                contador_vuelos=ContadorVuelos(),
                hooks={"pre_finished": lambda: (_ for _ in ()).throw(RuntimeError("crash"))},
            )

            coord1.iniciar_barrera("c1", b'{"client_id": "c1"}')

            with pytest.raises(RuntimeError, match="crash"):
                coord1._ejecutar_flush_y_notificar("c1", 0)

            coord1.cerrar()

        with patch("workers.base.coordinacion.coordinador.TransporteControl") as mock_trans2, \
             patch("workers.base.coordinacion.persistencia.PersistidorEstado") as mock_pe2:
            mock_pe2.return_value.directory = real_pe.directory
            mock_pe2.return_value.guardar = real_pe.guardar
            mock_pe2.return_value.cargar = real_pe.cargar
            mock_trans2.return_value.enviar = MagicMock()

            al_completar2 = MagicMock()
            coord2 = CoordinadorDistribuido(
                config,
                al_completar_sincronizacion=al_completar2,
                al_completar_barrera=MagicMock(),
                contador_vuelos=ContadorVuelos(),
            )

            assert "c1" in coord2._clientes

            coord2.cerrar()
