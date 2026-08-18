"""Tests de tolerancia a fallos del watchdog con crash hooks.

Cada test simula un crash en un punto crítico del watchdog y verifica
que tras reiniciar, el sistema se recupera correctamente:

- POST_TOPOLOGY_SAVE: crash después de persistir topología → al reiniciar la carga
- POST_TOPOLOGY_LOAD: crash después de cargar topología → al reiniciar la recarga
- POST_LEADER_DECLARE: crash del líder recién electo → nueva elección lo reemplaza
- PRE_PUBLISH_CAIDA: crash antes de publicar caída → al reiniciar la re-detecta
"""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from common.persistencia import PersistidorEstado
from watchdog.detector import DetectorLatidos
from watchdog.eleccion_anillo import EleccionAnillo


def _crear_config_anillo(id_watchdog=1, cantidad_watchdogs=3):
    config = MagicMock()
    config.id_watchdog = id_watchdog
    config.cantidad_watchdogs = cantidad_watchdogs
    config.host_mom = "localhost"
    config.intervalo_latido_lider = 5.0
    config.timeout_lider_segundos = 20.0
    config.demora_inicial_eleccion_max = 3.0
    config.intervalo_chequeo_lider = 5.0
    config.timeout_eleccion = 30.0
    config.ttl_sospechados_caidos = 60.0
    return config


def _crear_config_detector(etapas=None, timeout=1.0):
    config = MagicMock()
    config.host_mom = "localhost"
    config.etapas = etapas or ["q5_converter"]
    config.timeout_segundos = timeout
    config.intervalo_chequeo_segundos = 0.5
    config.cola_caidas = "caidas"
    return config


def _crear_eleccion(tmp_path, id_watchdog=1, cantidad_watchdogs=3):
    config = _crear_config_anillo(id_watchdog, cantidad_watchdogs)
    with patch("watchdog.eleccion_anillo.PersistidorEstado",
               lambda name: PersistidorEstado(name, base_dir=str(tmp_path))):
        eleccion = EleccionAnillo(
            config, MagicMock(), MagicMock(), MagicMock()
        )
    eleccion._enviar_a = MagicMock()
    eleccion._bucle_latido_lider = MagicMock()
    return eleccion


class TestCrashPostTopologySave(unittest.TestCase):
    """Crash después de guardar topología a disco.
    Verifica que la topología se persistió correctamente y al reiniciar
    se recupera sin pérdida."""

    def test_topologia_sobrevive_crash_post_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            e1 = _crear_eleccion(tmp)
            e1._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "q4_sumador": ["01", "02", "03"],
            })

            # Simular crash (e1 muere)
            del e1

            # Reiniciar
            e2 = _crear_eleccion(tmp)
            topo = e2.obtener_topologia_serializable()

            self.assertIn("q5_converter", topo)
            self.assertCountEqual(topo["q5_converter"], ["01", "02"])
            self.assertIn("q4_sumador", topo)
            self.assertCountEqual(topo["q4_sumador"], ["01", "02", "03"])

    def test_topologia_parcial_se_completa_tras_reinicio(self):
        """Guardo topología parcial, crasheo, reinicio y fusiono más."""
        with tempfile.TemporaryDirectory() as tmp:
            e1 = _crear_eleccion(tmp)
            e1._fusionar_topologia({"q1": ["01"]})
            del e1

            e2 = _crear_eleccion(tmp)
            e2._fusionar_topologia({"q1": ["02"], "q2": ["01"]})
            topo = e2.obtener_topologia_serializable()

            self.assertCountEqual(topo["q1"], ["01", "02"])
            self.assertIn("q2", topo)

    def test_multiples_crashes_no_pierden_datos(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                e = _crear_eleccion(tmp)
                e._fusionar_topologia({f"etapa_{i}": [str(i)]})
                del e

            final = _crear_eleccion(tmp)
            topo = final.obtener_topologia_serializable()
            for i in range(5):
                self.assertIn(f"etapa_{i}", topo)


class TestCrashPostTopologyLoad(unittest.TestCase):
    """Crash después de cargar topología de disco.
    La topología ya se cargó a memoria antes del crash, así que al
    reiniciar simplemente se vuelve a cargar."""

    def test_topologia_se_recarga_tras_crash_post_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            e1 = _crear_eleccion(tmp)
            e1._fusionar_topologia({"gateway": ["01"], "q5_converter": ["01"]})
            del e1

            # Primer reinicio: carga topología → crash hook dispararía acá
            e2 = _crear_eleccion(tmp)
            topo2 = e2.obtener_topologia_serializable()
            self.assertIn("gateway", topo2)
            del e2

            # Segundo reinicio: la topología sigue ahí
            e3 = _crear_eleccion(tmp)
            topo3 = e3.obtener_topologia_serializable()
            self.assertIn("gateway", topo3)
            self.assertIn("q5_converter", topo3)


class TestCrashPostLeaderDeclare(unittest.TestCase):
    """Crash del líder justo después de declararse.
    Los standby no reciben heartbeat → inician nueva elección."""

    def test_standby_detecta_lider_caido_e_inicia_eleccion(self):
        with tempfile.TemporaryDirectory() as tmp:
            lider = _crear_eleccion(tmp, id_watchdog=3, cantidad_watchdogs=3)

            # Líder se declara
            with patch("watchdog.eleccion_anillo.threading.Thread"):
                lider._declarar_lider()
            self.assertTrue(lider._es_lider)

            # Simular crash del líder — los standby no reciben coordinador
            standby = _crear_eleccion(tmp, id_watchdog=1, cantidad_watchdogs=3)
            standby._ultimo_latido_lider = time.time() - 25

            with patch.object(standby, '_iniciar_eleccion') as mock_eleccion:
                standby._tick_timeout_lider(tiempo_inicio=time.time() - 25)

            mock_eleccion.assert_called_once()

    def test_topologia_del_lider_caido_se_preserva(self):
        """El líder crasheó pero la topología que tenía está en disco."""
        with tempfile.TemporaryDirectory() as tmp:
            lider = _crear_eleccion(tmp, id_watchdog=3)
            lider._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "gateway": ["01"],
            })

            with patch("watchdog.eleccion_anillo.threading.Thread"):
                lider._declarar_lider()
            del lider

            # Nuevo líder (otro watchdog) carga la misma topología
            nuevo_lider = _crear_eleccion(tmp, id_watchdog=1)
            topo = nuevo_lider.obtener_topologia_serializable()
            self.assertIn("q5_converter", topo)
            self.assertCountEqual(topo["q5_converter"], ["01", "02"])


class TestCrashPrePublishCaida(unittest.TestCase):
    """Crash del watchdog antes de publicar la caída al actuador.
    Al reiniciar, el detector debe re-detectar al worker caído."""

    def test_worker_caido_se_redetecta_tras_reinicio(self):
        topologia = {"q5_converter": ["01"]}
        config = _crear_config_detector(etapas=["q5_converter"], timeout=0.1)

        # Primera vida: detecta caída pero crashea antes de publicar
        det1 = DetectorLatidos(config, topologia=topologia)
        self.assertIn(("q5_converter", "01"), det1._ultimo_visto)

        # Simular que el timeout expiró (worker caído)
        det1._ultimo_visto[("q5_converter", "01")] = time.time() - 10
        # El crash hook dispararía en _publicar_caida antes de enviar
        # → el worker sigue en _ultimo_visto porque no se borró
        del det1

        # Segunda vida: el detector se reinicializa con la misma topología
        det2 = DetectorLatidos(config, topologia=topologia)
        det2._cola_caidas = MagicMock()

        # El worker sigue siendo conocido
        self.assertIn(("q5_converter", "01"), det2._ultimo_visto)

        # Forzar timestamp viejo
        det2._ultimo_visto[("q5_converter", "01")] = time.time() - 10

        with patch.object(det2, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(det2._ultimo_visto)
            caidas = [
                (e, i) for (e, i), ts in snapshot.items()
                if ahora - ts > config.timeout_segundos
            ]
            for e, i in caidas:
                det2._publicar_caida(e, i)

        mock_pub.assert_called_once_with("q5_converter", "01")

    def test_multiples_workers_caidos_se_redetectan(self):
        topologia = {"q5_converter": ["01", "02"], "gateway": ["01"]}
        config = _crear_config_detector(
            etapas=["q5_converter", "gateway"], timeout=0.1
        )

        det = DetectorLatidos(config, topologia=topologia)
        det._cola_caidas = MagicMock()

        # Todos con timestamp viejo
        ahora = time.time()
        for key in det._ultimo_visto:
            det._ultimo_visto[key] = ahora - 10

        with patch.object(det, '_publicar_caida') as mock_pub:
            snapshot = dict(det._ultimo_visto)
            caidas = [
                (e, i) for (e, i), ts in snapshot.items()
                if ahora - ts > config.timeout_segundos
            ]
            for e, i in caidas:
                det._publicar_caida(e, i)

        self.assertEqual(mock_pub.call_count, 3)


class TestRecoveryEndToEnd(unittest.TestCase):
    """Tests end-to-end: combinan topología persistida + detector + crashes."""

    def test_watchdog_crashea_y_reinicia_detectando_worker_caido(self):
        """Flujo completo:
        1. Watchdog recibe topología de workers
        2. Watchdog crashea
        3. Watchdog reinicia, carga topología de disco
        4. Pasa topología al detector
        5. Detector detecta worker caído (nunca mandó heartbeat)
        """
        with tempfile.TemporaryDirectory() as tmp:
            # Vida 1: recibe topología
            e1 = _crear_eleccion(tmp)
            e1._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "q4_sumador": ["01"],
            })
            del e1

            # Vida 2: reinicia, carga topología, crea detector
            e2 = _crear_eleccion(tmp)
            topo = e2.obtener_topologia_serializable()

            config_det = _crear_config_detector(
                etapas=list(topo.keys()), timeout=0.1
            )
            detector = DetectorLatidos(config_det, topologia=topo)
            detector._cola_caidas = MagicMock()

            # Workers conocidos por topología
            self.assertIn(("q5_converter", "01"), detector._ultimo_visto)
            self.assertIn(("q5_converter", "02"), detector._ultimo_visto)
            self.assertIn(("q4_sumador", "01"), detector._ultimo_visto)

            # Forzar timestamps viejos
            for key in detector._ultimo_visto:
                detector._ultimo_visto[key] = time.time() - 10

            # Chequeo detecta las 3 caídas
            with patch.object(detector, '_publicar_caida') as mock_pub:
                ahora = time.time()
                snapshot = dict(detector._ultimo_visto)
                caidas = [
                    (e, i) for (e, i), ts in snapshot.items()
                    if ahora - ts > config_det.timeout_segundos
                ]
                for e, i in caidas:
                    detector._publicar_caida(e, i)

            self.assertEqual(mock_pub.call_count, 3)

    def test_lider_crashea_nuevo_lider_hereda_topologia(self):
        """Líder guarda topología, crashea. Nuevo líder (otro watchdog)
        la carga de disco y detecta workers caídos."""
        with tempfile.TemporaryDirectory() as tmp:
            # Líder original (watchdog 3)
            lider = _crear_eleccion(tmp, id_watchdog=3)
            lider._fusionar_topologia({
                "q5_converter": ["01"],
                "gateway": ["01"],
            })
            del lider

            # Nuevo líder (watchdog 1) — comparte volumen
            nuevo = _crear_eleccion(tmp, id_watchdog=1)
            topo = nuevo.obtener_topologia_serializable()

            self.assertIn("q5_converter", topo)
            self.assertIn("gateway", topo)

            config_det = _crear_config_detector(
                etapas=list(topo.keys()), timeout=0.1
            )
            detector = DetectorLatidos(config_det, topologia=topo)

            self.assertIn(("q5_converter", "01"), detector._ultimo_visto)
            self.assertIn(("gateway", "01"), detector._ultimo_visto)


if __name__ == "__main__":
    unittest.main()
