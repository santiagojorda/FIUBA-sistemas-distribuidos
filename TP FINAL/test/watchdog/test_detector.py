import json
import time
import unittest
from unittest.mock import MagicMock, patch

from watchdog.detector import DetectorLatidos


def crear_config(etapas=None, timeout=15.0, intervalo_chequeo=5.0):
    config = MagicMock()
    config.host_mom = "localhost"
    config.etapas = etapas or ["gateway", "filtro"]
    config.intervalo_latido_segundos = 5.0
    config.umbral_latidos_perdidos = 3
    config.timeout_segundos = timeout
    config.intervalo_chequeo_segundos = intervalo_chequeo
    config.cola_caidas = "caidas"
    return config


def crear_detector(etapas=None, timeout=15.0):
    config = crear_config(etapas=etapas, timeout=timeout)
    return DetectorLatidos(config)


def crear_msg_latido(etapa, instancia, ts=None):
    payload = {"etapa": etapa, "instancia": instancia, "timestamp": ts or time.time()}
    return json.dumps(payload).encode()


class TestAlRecibirLatido(unittest.TestCase):

    def test_registra_latido_en_ultimo_visto(self):
        detector = crear_detector()
        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("gateway", "1"), ack, None)
        self.assertIn(("gateway", "1"), detector._ultimo_visto)
        ack.assert_called_once()

    def test_actualiza_timestamp_con_latido_mas_reciente(self):
        detector = crear_detector()
        ack = MagicMock()
        ts_viejo = time.time() - 10
        ts_nuevo = time.time()
        detector._al_recibir_latido(crear_msg_latido("gateway", "1", ts=ts_viejo), ack, None)
        detector._al_recibir_latido(crear_msg_latido("gateway", "1", ts=ts_nuevo), ack, None)
        self.assertAlmostEqual(detector._ultimo_visto[("gateway", "1")], ts_nuevo, places=1)

    def test_latido_malformado_hace_ack_igual(self):
        detector = crear_detector()
        ack = MagicMock()
        detector._al_recibir_latido(b"no-es-json", ack, None)
        ack.assert_called_once()
        self.assertEqual(len(detector._ultimo_visto), 0)

    def test_multiples_instancias_de_misma_etapa(self):
        detector = crear_detector()
        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("filtro", "1"), ack, None)
        detector._al_recibir_latido(crear_msg_latido("filtro", "2"), ack, None)
        self.assertIn(("filtro", "1"), detector._ultimo_visto)
        self.assertIn(("filtro", "2"), detector._ultimo_visto)


class TestPublicarCaida(unittest.TestCase):

    def test_publica_evento_en_cola_caidas(self):
        detector = crear_detector()
        mock_cola = MagicMock()
        detector._cola_caidas = mock_cola
        detector._ultimo_visto[("gateway", "1")] = time.time() - 20

        detector._publicar_caida("gateway", "1")

        mock_cola.send.assert_called_once()
        enviado = json.loads(mock_cola.send.call_args[0][0].decode())
        self.assertEqual(enviado["etapa"], "gateway")
        self.assertEqual(enviado["instancia"], "1")

    def test_elimina_de_ultimo_visto_tras_publicar(self):
        detector = crear_detector()
        detector._cola_caidas = MagicMock()
        detector._ultimo_visto[("gateway", "1")] = time.time() - 20

        detector._publicar_caida("gateway", "1")

        self.assertNotIn(("gateway", "1"), detector._ultimo_visto)

    def test_crea_conexion_si_no_existe(self):
        detector = crear_detector()
        with patch("watchdog.detector.MessageMiddlewareQueueRabbitMQ") as mock_cls:
            mock_cls.return_value = MagicMock()
            detector._ultimo_visto[("filtro", "1")] = time.time() - 20
            detector._publicar_caida("filtro", "1")
        mock_cls.assert_called_once_with("localhost", "caidas")

    def test_reutiliza_conexion_existente(self):
        detector = crear_detector()
        mock_cola = MagicMock()
        detector._cola_caidas = mock_cola
        detector._ultimo_visto[("filtro", "1")] = time.time() - 20
        detector._ultimo_visto[("filtro", "2")] = time.time() - 20

        with patch("watchdog.detector.MessageMiddlewareQueueRabbitMQ") as mock_cls:
            detector._publicar_caida("filtro", "1")
            detector._publicar_caida("filtro", "2")

        mock_cls.assert_not_called()
        self.assertEqual(mock_cola.send.call_count, 2)


class TestBucleChequeo(unittest.TestCase):

    def test_no_reporta_worker_dentro_del_timeout(self):
        detector = crear_detector(timeout=15.0)
        detector._cola_caidas = MagicMock()
        detector._ultimo_visto[("gateway", "1")] = time.time() - 5

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            import copy
            snapshot = copy.deepcopy(detector._ultimo_visto)
            caidas = [
                (etapa, inst)
                for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_not_called()

    def test_reporta_worker_fuera_del_timeout(self):
        detector = crear_detector(timeout=15.0)
        detector._cola_caidas = MagicMock()
        detector._ultimo_visto[("gateway", "1")] = time.time() - 20

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            import copy
            snapshot = copy.deepcopy(detector._ultimo_visto)
            caidas = [
                (etapa, inst)
                for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_called_once_with("gateway", "1")


class TestDetectorConTopologiaPersistida(unittest.TestCase):
    """Verifica que el detector detecte caídas de workers que se conocen
    por topología (persistida en disco) pero nunca mandaron heartbeats."""

    def test_worker_conocido_por_topologia_se_detecta_como_caido(self):
        """Si la topología dice que q5_converter/01 existe, el detector
        lo agrega a _ultimo_visto al arrancar. Si nunca manda heartbeat,
        se detecta como caído tras el timeout."""
        topologia = {"q5_converter": ["01", "02"], "gateway": ["01"]}
        config = crear_config(etapas=["q5_converter", "gateway"], timeout=1.0)
        detector = DetectorLatidos(config, topologia=topologia)

        self.assertIn(("q5_converter", "01"), detector._ultimo_visto)
        self.assertIn(("q5_converter", "02"), detector._ultimo_visto)
        self.assertIn(("gateway", "01"), detector._ultimo_visto)

    def test_worker_conocido_se_detecta_caido_tras_timeout(self):
        topologia = {"q5_converter": ["01"]}
        config = crear_config(etapas=["q5_converter"], timeout=0.1)
        detector = DetectorLatidos(config, topologia=topologia)
        detector._cola_caidas = MagicMock()

        # Forzar timestamp viejo para simular timeout
        detector._ultimo_visto[("q5_converter", "01")] = time.time() - 1

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(detector._ultimo_visto)
            caidas = [
                (etapa, inst) for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_called_once_with("q5_converter", "01")

    def test_sin_topologia_detector_no_tiene_workers_conocidos(self):
        config = crear_config(etapas=["q5_converter"])
        detector = DetectorLatidos(config)
        self.assertEqual(len(detector._ultimo_visto), 0)

    def test_worker_que_manda_heartbeat_no_se_reporta(self):
        """Worker conocido por topología que manda heartbeat a tiempo
        no se reporta como caído."""
        topologia = {"gateway": ["01"]}
        config = crear_config(etapas=["gateway"], timeout=5.0)
        detector = DetectorLatidos(config, topologia=topologia)

        # Heartbeat reciente
        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("gateway", "01"), ack, None)

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(detector._ultimo_visto)
            caidas = [
                (etapa, inst) for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_not_called()


class TestDetectorWorkerInvisible(unittest.TestCase):
    """Verifica el escenario donde un worker nunca se registró
    y nunca mandó heartbeat — sin topología es invisible."""

    def test_worker_sin_registro_ni_heartbeat_es_invisible(self):
        config = crear_config(etapas=["q5_converter"], timeout=0.1)
        detector = DetectorLatidos(config)
        detector._cola_caidas = MagicMock()

        time.sleep(0.15)

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(detector._ultimo_visto)
            caidas = [
                (etapa, inst) for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_not_called()

    def test_worker_invisible_se_detecta_con_topologia(self):
        """Mismo escenario pero con topología: el worker se detecta."""
        topologia = {"q5_converter": ["01"]}
        config = crear_config(etapas=["q5_converter"], timeout=0.1)
        detector = DetectorLatidos(config, topologia=topologia)
        detector._cola_caidas = MagicMock()

        # Forzar timestamp viejo
        detector._ultimo_visto[("q5_converter", "01")] = time.time() - 1

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(detector._ultimo_visto)
            caidas = [
                (etapa, inst) for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_called_once_with("q5_converter", "01")

    def test_publicar_caida_borra_worker_de_ultimo_visto(self):
        """Tras publicar caída, el worker desaparece de _ultimo_visto.
        Si no vuelve a registrarse, no se vuelve a detectar."""
        topologia = {"q5_converter": ["01"]}
        config = crear_config(etapas=["q5_converter"], timeout=0.1)
        detector = DetectorLatidos(config, topologia=topologia)
        detector._cola_caidas = MagicMock()
        detector._ultimo_visto[("q5_converter", "01")] = time.time() - 1

        detector._publicar_caida("q5_converter", "01")

        self.assertNotIn(("q5_converter", "01"), detector._ultimo_visto)

    def test_worker_reaparece_tras_caida_publicada(self):
        """Tras publicar caída, si el worker manda heartbeat, vuelve
        a ser monitoreado."""
        topologia = {"q5_converter": ["01"]}
        config = crear_config(etapas=["q5_converter"], timeout=0.1)
        detector = DetectorLatidos(config, topologia=topologia)
        detector._cola_caidas = MagicMock()
        detector._ultimo_visto[("q5_converter", "01")] = time.time() - 1

        detector._publicar_caida("q5_converter", "01")
        self.assertNotIn(("q5_converter", "01"), detector._ultimo_visto)

        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("q5_converter", "01"), ack, None)
        self.assertIn(("q5_converter", "01"), detector._ultimo_visto)


class TestFormatoInstanciaConsistente(unittest.TestCase):
    """Verifica que la topología y los heartbeats usen el mismo formato de
    instancia (zero-padded '01', '02', etc.) para evitar falsos positivos."""

    def test_topologia_zero_padded_matchea_heartbeat(self):
        """Si la topología usa '01' y el heartbeat envía '01', no hay
        timeout espurio."""
        topologia = {"q5_counter": ["01"]}
        config = crear_config(etapas=["q5_counter"], timeout=5.0)
        detector = DetectorLatidos(config, topologia=topologia)

        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("q5_counter", "01"), ack, None)

        ahora = time.time()
        snapshot = dict(detector._ultimo_visto)
        caidas = [
            (e, i) for (e, i), ts in snapshot.items()
            if ahora - ts > config.timeout_segundos
        ]
        self.assertEqual(caidas, [])

    def test_topologia_sin_zero_pad_no_matchea_heartbeat(self):
        """Si la topología tiene '1' pero el heartbeat envía '01',
        son keys distintas y la entry '1' nunca se actualiza → false positive.
        Este test documenta el bug que existía antes del fix."""
        topologia = {"q5_counter": ["1"]}
        config = crear_config(etapas=["q5_counter"], timeout=0.1)
        detector = DetectorLatidos(config, topologia=topologia)

        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("q5_counter", "01"), ack, None)

        # Forzar timeout de la entry "1" que nunca fue actualizada
        detector._ultimo_visto[("q5_counter", "1")] = time.time() - 1

        ahora = time.time()
        snapshot = dict(detector._ultimo_visto)
        caidas = [
            (e, i) for (e, i), ts in snapshot.items()
            if ahora - ts > config.timeout_segundos
        ]
        # Hay dos entries: ("q5_counter","1") vieja y ("q5_counter","01") nueva
        self.assertEqual(len(detector._ultimo_visto), 2)
        self.assertEqual(len(caidas), 1)
        self.assertEqual(caidas[0], ("q5_counter", "1"))

    def test_multiples_instancias_zero_padded_en_topologia(self):
        topologia = {"q5_filter": ["01", "02", "03"]}
        config = crear_config(etapas=["q5_filter"], timeout=5.0)
        detector = DetectorLatidos(config, topologia=topologia)

        ack = MagicMock()
        for inst in ["01", "02", "03"]:
            detector._al_recibir_latido(crear_msg_latido("q5_filter", inst), ack, None)

        ahora = time.time()
        snapshot = dict(detector._ultimo_visto)
        caidas = [
            (e, i) for (e, i), ts in snapshot.items()
            if ahora - ts > config.timeout_segundos
        ]
        self.assertEqual(caidas, [])
        self.assertEqual(len(detector._ultimo_visto), 3)


class TestRegistrarNodo(unittest.TestCase):

    def test_registra_nodo_nuevo_en_ultimo_visto(self):
        detector = crear_detector()
        detector.registrar_nodo("q5_converter", "02")
        self.assertIn(("q5_converter", "02"), detector._ultimo_visto)

    def test_no_sobreescribe_nodo_existente(self):
        detector = crear_detector()
        ts_original = time.time() - 10
        detector._ultimo_visto[("q5_converter", "01")] = ts_original
        detector.registrar_nodo("q5_converter", "01")
        self.assertAlmostEqual(
            detector._ultimo_visto[("q5_converter", "01")], ts_original, places=1
        )

    def test_nodo_registrado_sin_heartbeat_se_detecta_como_caido(self):
        detector = crear_detector(timeout=0.1)
        detector._cola_caidas = MagicMock()
        detector.registrar_nodo("q5_converter", "02")

        detector._ultimo_visto[("q5_converter", "02")] = time.time() - 1

        with patch.object(detector, '_publicar_caida') as mock_pub:
            ahora = time.time()
            snapshot = dict(detector._ultimo_visto)
            caidas = [
                (etapa, inst) for (etapa, inst), ts in snapshot.items()
                if ahora - ts > detector._config.timeout_segundos
            ]
            for etapa, inst in caidas:
                detector._publicar_caida(etapa, inst)

        mock_pub.assert_called_once_with("q5_converter", "02")

    def test_nodo_registrado_con_heartbeat_posterior_no_se_detecta(self):
        detector = crear_detector(timeout=5.0)
        detector.registrar_nodo("q5_converter", "02")

        ack = MagicMock()
        detector._al_recibir_latido(crear_msg_latido("q5_converter", "02"), ack, None)

        ahora = time.time()
        snapshot = dict(detector._ultimo_visto)
        caidas = [
            (etapa, inst) for (etapa, inst), ts in snapshot.items()
            if ahora - ts > detector._config.timeout_segundos
        ]
        self.assertEqual(caidas, [])


if __name__ == "__main__":
    unittest.main()
