import json
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from watchdog.eleccion_anillo import EleccionAnillo


def crear_config(id_watchdog=1, cantidad_watchdogs=3):
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


def crear_eleccion(id_watchdog=1, cantidad_watchdogs=3, tmp_path=None, al_registrar_nodo=None):
    config = crear_config(id_watchdog, cantidad_watchdogs)
    al_ser_lider = MagicMock()
    al_perder_liderazgo = MagicMock()
    al_caer_standby = MagicMock()
    patches = [
        patch("watchdog.eleccion_anillo.PersistidorEstado"),
    ]
    if tmp_path is not None:
        from common.persistencia import PersistidorEstado
        patches = [
            patch("watchdog.eleccion_anillo.PersistidorEstado",
                  lambda name: PersistidorEstado(name, base_dir=str(tmp_path))),
        ]
    for p in patches:
        p.start()
    eleccion = EleccionAnillo(config, al_ser_lider, al_perder_liderazgo, al_caer_standby, al_registrar_nodo)
    for p in patches:
        p.stop()
    eleccion._enviar_a = MagicMock()
    eleccion._bucle_latido_lider = MagicMock()
    return eleccion, al_ser_lider, al_perder_liderazgo, al_caer_standby


class TestCalcularProximoDestino(unittest.TestCase):

    def test_devuelve_siguiente_directo_si_no_hay_muertos(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        with eleccion._lock:
            destino = eleccion._calcular_proximo_destino()
        self.assertEqual(destino, 2)

    def test_saltea_nodo_sospechado(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ids_sospechados_caidos[2] = time.time()
        with eleccion._lock:
            destino = eleccion._calcular_proximo_destino()
        self.assertEqual(destino, 3)

    def test_saltea_multiples_nodos_sospechados(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ids_sospechados_caidos[2] = time.time()
        eleccion._ids_sospechados_caidos[3] = time.time()
        with eleccion._lock:
            destino = eleccion._calcular_proximo_destino()
        self.assertEqual(destino, 1)

    def test_no_saltea_nodo_con_ttl_expirado(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ids_sospechados_caidos[2] = time.time() - 61
        with eleccion._lock:
            destino = eleccion._calcular_proximo_destino()
        self.assertEqual(destino, 2)


class TestManejarEleccion(unittest.TestCase):

    def test_propio_id_declara_lider(self):
        eleccion, al_ser_lider, *_ = crear_eleccion(id_watchdog=2)
        with patch.object(eleccion, '_declarar_lider') as mock_declarar:
            eleccion._manejar_eleccion(id_recibido=2, saltar=[])
        mock_declarar.assert_called_once()

    def test_id_mayor_se_reenvia_sin_cambio(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._manejar_eleccion(id_recibido=3, saltar=[])
        eleccion._enviar_a.assert_called_once()
        _, payload = eleccion._enviar_a.call_args[0]
        self.assertEqual(payload["id"], 3)

    def test_id_menor_se_reemplaza_por_propio(self):
        eleccion, *_ = crear_eleccion(id_watchdog=3)
        eleccion._manejar_eleccion(id_recibido=1, saltar=[])
        eleccion._enviar_a.assert_called_once()
        _, payload = eleccion._enviar_a.call_args[0]
        self.assertEqual(payload["id"], 3)

    def test_lider_absorbe_mensaje(self):
        eleccion, *_ = crear_eleccion(id_watchdog=2)
        eleccion._es_lider = True
        eleccion._manejar_eleccion(id_recibido=1, saltar=[])
        eleccion._enviar_a.assert_not_called()

    def test_lider_activo_conocido_absorbe_mensaje(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._id_lider = 3
        eleccion._ultimo_latido_lider = time.time()
        eleccion._manejar_eleccion(id_recibido=2, saltar=[])
        eleccion._enviar_a.assert_not_called()

    def test_propagacion_de_saltar(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._manejar_eleccion(id_recibido=3, saltar=[2])
        self.assertIn(2, eleccion._ids_sospechados_caidos)

    def test_saltar_no_sobreescribe_timestamp_existente(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        ts_original = time.time() - 10
        eleccion._ids_sospechados_caidos[2] = ts_original
        eleccion._manejar_eleccion(id_recibido=3, saltar=[2])
        self.assertAlmostEqual(eleccion._ids_sospechados_caidos[2], ts_original, places=1)


class TestDeclararLider(unittest.TestCase):

    def test_llama_al_ser_lider_con_nodos_caidos(self):
        eleccion, al_ser_lider, *_ = crear_eleccion(id_watchdog=3)
        eleccion._ids_sospechados_caidos[1] = time.time()
        with patch("watchdog.eleccion_anillo.threading.Thread"):
            eleccion._declarar_lider()
        al_ser_lider.assert_called_once()
        ids_caidos = al_ser_lider.call_args[0][0]
        self.assertIn(1, ids_caidos)

    def test_idempotente_si_ya_es_lider(self):
        eleccion, al_ser_lider, *_ = crear_eleccion(id_watchdog=3)
        with patch("watchdog.eleccion_anillo.threading.Thread"):
            eleccion._declarar_lider()
            eleccion._declarar_lider()
        al_ser_lider.assert_called_once()

    def test_envia_coordinador_al_siguiente(self):
        eleccion, *_ = crear_eleccion(id_watchdog=3)
        with patch("watchdog.eleccion_anillo.threading.Thread"):
            eleccion._declarar_lider()
        eleccion._enviar_a.assert_called_once()
        _, payload = eleccion._enviar_a.call_args[0]
        self.assertEqual(payload["tipo"], "coordinador")
        self.assertEqual(payload["id"], 3)

    def test_excluye_nodos_caidos_con_ttl_expirado(self):
        eleccion, al_ser_lider, *_ = crear_eleccion(id_watchdog=3)
        eleccion._ids_sospechados_caidos[1] = time.time() - 61
        with patch("watchdog.eleccion_anillo.threading.Thread"):
            eleccion._declarar_lider()
        ids_caidos = al_ser_lider.call_args[0][0]
        self.assertNotIn(1, ids_caidos)


class TestManejarCoordinador(unittest.TestCase):

    def test_registra_nuevo_lider(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._manejar_coordinador(id_lider=3)
        self.assertEqual(eleccion._id_lider, 3)
        self.assertFalse(eleccion._es_lider)

    def test_reenvia_coordinador_si_no_lo_hizo(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._manejar_coordinador(id_lider=3)
        eleccion._enviar_a.assert_called_once()
        _, payload = eleccion._enviar_a.call_args[0]
        self.assertEqual(payload["tipo"], "coordinador")

    def test_no_reenvia_coordinador_duplicado(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._manejar_coordinador(id_lider=3)
        eleccion._manejar_coordinador(id_lider=3)
        self.assertEqual(eleccion._enviar_a.call_count, 1)

    def test_cede_liderazgo_si_era_lider(self):
        eleccion, _, al_perder_liderazgo, _ = crear_eleccion(id_watchdog=2)
        eleccion._es_lider = True
        eleccion._manejar_coordinador(id_lider=3)
        al_perder_liderazgo.assert_called_once()

    def test_ignora_coordinador_con_propio_id_si_es_lider(self):
        eleccion, _, al_perder_liderazgo, _ = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._manejar_coordinador(id_lider=3)
        al_perder_liderazgo.assert_not_called()


class TestManejarVivo(unittest.TestCase):

    def test_elimina_de_sospechados(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ids_sospechados_caidos[2] = time.time()
        eleccion._manejar_vivo(id_nodo=2)
        self.assertNotIn(2, eleccion._ids_sospechados_caidos)

    def test_lider_actualiza_ultimo_visto_standby(self):
        eleccion, *_ = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._standbys_caidos_reportados.add(1)
        eleccion._manejar_vivo(id_nodo=1)
        self.assertIn(1, eleccion._ultimo_visto_standby)
        self.assertNotIn(1, eleccion._standbys_caidos_reportados)


class TestTickTimeoutLider(unittest.TestCase):

    def test_no_actua_si_es_lider(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._es_lider = True
        with patch.object(eleccion, '_iniciar_eleccion') as mock_init:
            eleccion._tick_timeout_lider(tiempo_inicio=time.time())
        mock_init.assert_not_called()

    def test_no_actua_si_no_expiro_timeout(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ultimo_latido_lider = time.time()
        with patch.object(eleccion, '_iniciar_eleccion') as mock_init:
            eleccion._tick_timeout_lider(tiempo_inicio=time.time())
        mock_init.assert_not_called()

    def test_inicia_eleccion_al_expirar_timeout(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ultimo_latido_lider = time.time() - 25
        eleccion._id_lider = 3
        with patch.object(eleccion, '_iniciar_eleccion') as mock_init:
            eleccion._tick_timeout_lider(tiempo_inicio=time.time() - 25)
        mock_init.assert_called_once()
        self.assertIn(3, eleccion._ids_sospechados_caidos)

    def test_espera_si_eleccion_en_curso_sin_timeout(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ultimo_latido_lider = time.time() - 25
        eleccion._en_eleccion = True
        eleccion._eleccion_iniciada_en = time.time() - 5
        with patch.object(eleccion, '_iniciar_eleccion') as mock_init:
            eleccion._tick_timeout_lider(tiempo_inicio=time.time() - 25)
        mock_init.assert_not_called()

    def test_reintenta_si_eleccion_expiro(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._ultimo_latido_lider = time.time() - 25
        eleccion._en_eleccion = True
        eleccion._eleccion_iniciada_en = time.time() - 35
        with patch.object(eleccion, '_iniciar_eleccion') as mock_init:
            eleccion._tick_timeout_lider(tiempo_inicio=time.time() - 25)
        mock_init.assert_called_once()


class TestTickChequeoStandbys(unittest.TestCase):

    def test_no_actua_si_no_es_lider(self):
        eleccion, _, _, al_caer_standby = crear_eleccion(id_watchdog=3)
        eleccion._tick_chequeo_standbys()
        al_caer_standby.assert_not_called()

    def test_no_actua_durante_periodo_de_gracia(self):
        eleccion, _, _, al_caer_standby = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._lider_desde = time.time()
        eleccion._tick_chequeo_standbys()
        al_caer_standby.assert_not_called()

    def test_detecta_standby_silencioso(self):
        eleccion, _, _, al_caer_standby = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._lider_desde = time.time() - 25
        eleccion._tick_chequeo_standbys()
        llamadas = [c[0][0] for c in al_caer_standby.call_args_list]
        self.assertIn(1, llamadas)
        self.assertIn(2, llamadas)

    def test_no_reporta_standby_dos_veces(self):
        eleccion, _, _, al_caer_standby = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._lider_desde = time.time() - 25
        eleccion._tick_chequeo_standbys()
        eleccion._tick_chequeo_standbys()
        self.assertEqual(al_caer_standby.call_count, 2)

    def test_standby_vuelve_a_mandar_latido_sale_de_reportados(self):
        eleccion, _, _, al_caer_standby = crear_eleccion(id_watchdog=3)
        eleccion._es_lider = True
        eleccion._lider_desde = time.time() - 25
        eleccion._tick_chequeo_standbys()
        eleccion._manejar_latido_standby(id_nodo=1)
        eleccion._tick_chequeo_standbys()
        total_llamadas_nodo_1 = sum(1 for c in al_caer_standby.call_args_list if c[0][0] == 1)
        self.assertEqual(total_llamadas_nodo_1, 1)


class TestIniciarEleccionTimeout(unittest.TestCase):

    def test_timeout_agrega_ultimo_destino_a_sospechados(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._en_eleccion = True
        eleccion._eleccion_iniciada_en = time.time() - 35
        eleccion._ultimo_destino_eleccion = 2
        eleccion._iniciar_eleccion()
        self.assertIn(2, eleccion._ids_sospechados_caidos)

    def test_no_reintenta_si_eleccion_vigente(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._en_eleccion = True
        eleccion._eleccion_iniciada_en = time.time() - 5
        eleccion._iniciar_eleccion()
        eleccion._enviar_a.assert_not_called()


class TestTopologiaPersistida(unittest.TestCase):
    """Verifica que la topología se persista en disco y se cargue al reiniciar."""

    def test_fusionar_topologia_guarda_a_disco(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            eleccion._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "gateway": ["01"],
            })

            topo = eleccion.obtener_topologia_serializable()
            self.assertIn("q5_converter", topo)
            self.assertIn("01", topo["q5_converter"])
            self.assertIn("02", topo["q5_converter"])

            archivo = os.path.join(tmp, "topologia", "estado.json")
            self.assertTrue(os.path.exists(archivo))
            with open(archivo) as f:
                guardado = json.load(f)
            self.assertIn("q5_converter", guardado)

    def test_topologia_se_carga_de_disco_al_reiniciar(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion1, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            eleccion1._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "q4_sumador": ["01"],
            })

            eleccion2, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            topo = eleccion2.obtener_topologia_serializable()
            self.assertIn("q5_converter", topo)
            self.assertCountEqual(topo["q5_converter"], ["01", "02"])
            self.assertIn("q4_sumador", topo)

    def test_fusionar_no_sobreescribe_instancias_existentes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            eleccion._fusionar_topologia({"q1": ["01", "02"]})
            eleccion._fusionar_topologia({"q1": ["03"]})

            topo = eleccion.obtener_topologia_serializable()
            self.assertCountEqual(topo["q1"], ["01", "02", "03"])

    def test_fusionar_none_no_falla(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._fusionar_topologia(None)
        self.assertEqual(eleccion.obtener_topologia_serializable(), {})

    def test_fusionar_sin_cambio_no_escribe_a_disco(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            eleccion._fusionar_topologia({"q1": ["01"]})

            with patch.object(eleccion._persistidor_topologia, 'guardar') as mock_guardar:
                eleccion._fusionar_topologia({"q1": ["01"]})
                mock_guardar.assert_not_called()

    def test_topologia_vacia_en_disco_arranca_limpia(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            topo = eleccion.obtener_topologia_serializable()
            self.assertEqual(topo, {})


class TestRetryConsumidores(unittest.TestCase):
    """Verifica que los hilos consumidores reconectan tras perder conexión."""

    def test_consumir_anillo_reintenta_tras_error(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        intentos = []

        def mock_constructor(host, nombre_cola):
            intentos.append(1)
            if len(intentos) <= 2:
                raise ConnectionError("simulación de desconexión")
            mock_cola = MagicMock()
            mock_cola.start_consuming = MagicMock(side_effect=lambda cb: eleccion._evento_parada.set())
            return mock_cola

        with patch("watchdog.eleccion_anillo.MessageMiddlewareQueueRabbitMQ", side_effect=mock_constructor):
            eleccion._consumir_anillo()

        self.assertEqual(len(intentos), 3)

    def test_consumir_latido_lider_reintenta_tras_error(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        intentos = []

        def mock_constructor(host, nombre_cola, exchange):
            intentos.append(1)
            if len(intentos) <= 1:
                raise ConnectionError("simulación de desconexión")
            mock_cola = MagicMock()
            mock_cola.start_consuming = MagicMock(side_effect=lambda cb: eleccion._evento_parada.set())
            return mock_cola

        with patch("watchdog.eleccion_anillo.FanoutQueueRabbitMQ", side_effect=mock_constructor):
            eleccion._consumir_latido_lider()

        self.assertEqual(len(intentos), 2)

    def test_consumir_anillo_para_limpiamente_con_evento_parada(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)

        def mock_constructor(host, nombre_cola):
            raise ConnectionError("simulación")

        eleccion._evento_parada.set()

        with patch("watchdog.eleccion_anillo.MessageMiddlewareQueueRabbitMQ", side_effect=mock_constructor):
            eleccion._consumir_anillo()

    def test_consumir_registro_topologia_reintenta_tras_error(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        intentos = []

        def mock_constructor(host, nombre_cola, exchange):
            intentos.append(1)
            if len(intentos) <= 1:
                raise ConnectionError("simulación de desconexión")
            mock_cola = MagicMock()
            mock_cola.start_consuming = MagicMock(side_effect=lambda cb: eleccion._evento_parada.set())
            return mock_cola

        with patch("watchdog.eleccion_anillo.FanoutQueueRabbitMQ", side_effect=mock_constructor):
            eleccion._consumir_registro_topologia()

        self.assertEqual(len(intentos), 2)


class TestTopologiaEndToEnd(unittest.TestCase):
    """Test end-to-end: topología persistida permite al detector
    conocer workers que nunca mandaron heartbeat."""

    def test_topologia_persistida_se_pasa_al_detector(self):
        """Simula el flujo: eleccion guarda topología → reinicia →
        la topología cargada de disco se pasa al detector."""
        import tempfile
        from watchdog.detector import DetectorLatidos

        with tempfile.TemporaryDirectory() as tmp:
            eleccion1, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            eleccion1._fusionar_topologia({
                "q5_converter": ["01", "02"],
                "gateway": ["01"],
            })

            eleccion2, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            topo = eleccion2.obtener_topologia_serializable()

            config_det = MagicMock()
            config_det.host_mom = "localhost"
            config_det.etapas = list(topo.keys())
            config_det.timeout_segundos = 1.0
            config_det.intervalo_chequeo_segundos = 0.5
            config_det.cola_caidas = "caidas"

            detector = DetectorLatidos(config_det, topologia=topo)

            self.assertIn(("q5_converter", "01"), detector._ultimo_visto)
            self.assertIn(("q5_converter", "02"), detector._ultimo_visto)
            self.assertIn(("gateway", "01"), detector._ultimo_visto)


class TestNormalizacionInstanciaTopologia(unittest.TestCase):
    """Verifica que las instancias en la topología se normalicen a formato
    zero-padded ('01', '02') para coincidir con el formato de heartbeats."""

    def test_cargar_topologia_normaliza_ids_numericos(self):
        """IDs numéricos sin zero-pad ('1', '2') deben normalizarse a '01', '02'."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eleccion, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            # Simular topología guardada con formato viejo (sin zero-pad)
            eleccion._fusionar_topologia({"q5_counter": ["1", "2"]})

            # Recargar (simula reinicio)
            eleccion2, *_ = crear_eleccion(id_watchdog=1, tmp_path=tmp)
            topo = eleccion2.obtener_topologia_serializable()

            self.assertIn("01", topo["q5_counter"])
            self.assertIn("02", topo["q5_counter"])
            self.assertNotIn("1", topo["q5_counter"])
            self.assertNotIn("2", topo["q5_counter"])

    def test_fusionar_topologia_normaliza_ids_numericos(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._fusionar_topologia({"gateway": ["1", "2", "3"]})
        topo = eleccion.obtener_topologia_serializable()
        self.assertCountEqual(topo["gateway"], ["01", "02", "03"])

    def test_fusionar_topologia_ids_ya_zero_padded_no_cambian(self):
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._fusionar_topologia({"gateway": ["01", "02"]})
        topo = eleccion.obtener_topologia_serializable()
        self.assertCountEqual(topo["gateway"], ["01", "02"])

    def test_fusionar_topologia_mixto_no_duplica(self):
        """Si llega '1' y luego '01', no debe haber dos entries."""
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._fusionar_topologia({"q1": ["1"]})
        eleccion._fusionar_topologia({"q1": ["01"]})
        topo = eleccion.obtener_topologia_serializable()
        self.assertEqual(len(topo["q1"]), 1)
        self.assertIn("01", topo["q1"])

    def test_fusionar_topologia_enteros_se_normalizan(self):
        """IDs que vienen como enteros (no strings) se normalizan."""
        eleccion, *_ = crear_eleccion(id_watchdog=1)
        eleccion._fusionar_topologia({"q1": [1, 2, 3]})
        topo = eleccion.obtener_topologia_serializable()
        self.assertCountEqual(topo["q1"], ["01", "02", "03"])


class TestCallbackRegistroNodo(unittest.TestCase):
    """Verifica que al_registrar_nodo se invoque al recibir un registro dinámico."""

    def _simular_registro(self, eleccion, etapa, instancia):
        payload = json.dumps({"etapa": etapa, "instancia": instancia}).encode()
        ack = MagicMock()
        # Invocar directamente el handler interno de _consumir_registro_topologia
        # simulando un mensaje recibido.
        # Para esto, llamamos al callback que _consumir_registro_topologia pasaría
        # a start_consuming. Extraemos la lógica capturando el callback.
        callback_capturado = []

        def mock_constructor(host, nombre_cola, exchange):
            mock_cola = MagicMock()
            def capturar_cb(cb):
                callback_capturado.append(cb)
                cb(payload, ack, None)
                eleccion._evento_parada.set()
            mock_cola.start_consuming = capturar_cb
            return mock_cola

        with patch("watchdog.eleccion_anillo.FanoutQueueRabbitMQ", side_effect=mock_constructor):
            eleccion._consumir_registro_topologia()

        return ack

    def test_callback_invocado_con_nodo_nuevo(self):
        al_registrar = MagicMock()
        eleccion, *_ = crear_eleccion(al_registrar_nodo=al_registrar)

        self._simular_registro(eleccion, "q5_converter", "02")

        al_registrar.assert_called_once_with("q5_converter", "02")

    def test_callback_no_invocado_si_nodo_ya_existe(self):
        al_registrar = MagicMock()
        eleccion, *_ = crear_eleccion(al_registrar_nodo=al_registrar)

        with eleccion._lock_topologia:
            eleccion._topologia["q5_converter"] = {"02"}

        self._simular_registro(eleccion, "q5_converter", "02")

        al_registrar.assert_not_called()

    def test_callback_none_no_falla(self):
        eleccion, *_ = crear_eleccion(al_registrar_nodo=None)
        self._simular_registro(eleccion, "q5_converter", "01")

    def test_callback_recibe_instancia_normalizada(self):
        al_registrar = MagicMock()
        eleccion, *_ = crear_eleccion(al_registrar_nodo=al_registrar)

        self._simular_registro(eleccion, "q5_converter", "2")

        al_registrar.assert_called_once_with("q5_converter", "02")


if __name__ == "__main__":
    unittest.main()
