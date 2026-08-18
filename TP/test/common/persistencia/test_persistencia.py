"""
Tests para PersistidorEstado y DedupFilter
==========================================
Cubren:
  - Caso 2: escritura atómica (estado nunca queda corrupto ante caídas)
  - Caso 3: deduplicación por request_id
"""
import os
import tempfile
import pytest
from common.persistencia import PersistidorEstado
from common.dedup_filter import DedupFilter


# ──────────────────────────────────────────────────────────────────
# Caso 2 — Escritura atómica
# ──────────────────────────────────────────────────────────────────

class TestPersistidorEstado:

    def test_guardar_y_cargar_roundtrip(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        estado = {"count": 42, "vistos": ["a", "b"]}
        p.guardar(estado)
        assert p.cargar() == estado

    def test_cargar_sin_estado_devuelve_dict_vacio(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        assert p.cargar() == {}

    def test_guardar_sobreescribe_estado_anterior(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        p.guardar({"count": 1})
        p.guardar({"count": 2})
        assert p.cargar() == {"count": 2}

    def test_borrar_elimina_el_estado(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        p.guardar({"count": 5})
        p.borrar()
        assert p.cargar() == {}

    def test_borrar_sin_estado_previo_no_falla(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        p.borrar()  # no debe lanzar

    def test_no_quedan_archivos_temporales_tras_guardado_exitoso(self, tmp_path):
        """Garantiza que el archivo temp_* se elimina después del os.replace."""
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        p.guardar({"count": 1})
        directorio = os.path.join(str(tmp_path), "nodo")
        temp_files = [f for f in os.listdir(directorio) if f.startswith("temp_")]
        assert temp_files == []

    def test_estado_anterior_sobrevive_si_escritura_nueva_se_interrumpe(self, tmp_path):
        """
        Simula un crash a mitad de escritura: escribe el temp pero no hace
        os.replace. El estado previo (estado.json) debe permanecer intacto.
        """
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        p.guardar({"count": 99})

        # Simular crash: crear el temp file pero no reemplazar
        directorio = os.path.join(str(tmp_path), "nodo")
        fd, temp_path = tempfile.mkstemp(dir=directorio, prefix="temp_estado_", suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write('{"count": 0}')
        os.remove(temp_path)  # eliminamos sin hacer replace → simula crash post-fsync

        assert p.cargar() == {"count": 99}

    def test_cargar_archivo_corrupto_lanza_runtime_error(self, tmp_path):
        p = PersistidorEstado("nodo", base_dir=str(tmp_path))
        directorio = os.path.join(str(tmp_path), "nodo")
        os.makedirs(directorio, exist_ok=True)
        with open(os.path.join(directorio, "estado.json"), "w") as f:
            f.write("{json invalido: sin comillas}")
        with pytest.raises(RuntimeError, match="corrupto"):
            p.cargar()

    def test_multiples_nodos_no_se_interfieren(self, tmp_path):
        p1 = PersistidorEstado("nodo_1", base_dir=str(tmp_path))
        p2 = PersistidorEstado("nodo_2", base_dir=str(tmp_path))
        p1.guardar({"id": "nodo1"})
        p2.guardar({"id": "nodo2"})
        assert p1.cargar() == {"id": "nodo1"}
        assert p2.cargar() == {"id": "nodo2"}


# ──────────────────────────────────────────────────────────────────
# Caso 3 — Deduplicación por request_id
# ──────────────────────────────────────────────────────────────────

class TestDedupFilter:

    def test_mensaje_nuevo_no_es_duplicado(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        assert not d.es_duplicado("c1", "req-1")

    def test_mensaje_marcado_es_duplicado(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        d.marcar_procesado("c1", "req-1")
        assert d.es_duplicado("c1", "req-1")

    def test_request_id_none_nunca_es_duplicado(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        d.marcar_procesado("c1", None)
        assert not d.es_duplicado("c1", None)

    def test_mismo_id_en_cliente_diferente_no_es_duplicado(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        d.marcar_procesado("c1", "req-1")
        assert not d.es_duplicado("c2", "req-1")

    def test_estado_persiste_entre_instancias(self, tmp_path):
        """Simula restart: nueva instancia carga IDs del disco."""
        d1 = DedupFilter("nodo", base_dir=str(tmp_path))
        d1.marcar_procesado("c1", "req-1")
        d1.marcar_procesado("c1", "req-2")
        d1._persistir()  # fuerza flush antes del "restart" (batch size es 50)

        d2 = DedupFilter("nodo", base_dir=str(tmp_path))
        assert d2.es_duplicado("c1", "req-1")
        assert d2.es_duplicado("c1", "req-2")
        assert not d2.es_duplicado("c1", "req-3")

    def test_limpiar_cliente_elimina_sus_ids(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        d.marcar_procesado("c1", "req-1")
        d.limpiar_cliente("c1")
        assert not d.es_duplicado("c1", "req-1")

    def test_limpiar_cliente_no_afecta_otros_clientes(self, tmp_path):
        d = DedupFilter("nodo", base_dir=str(tmp_path))
        d.marcar_procesado("c1", "req-1")
        d.marcar_procesado("c2", "req-1")
        d.limpiar_cliente("c1")
        assert d.es_duplicado("c2", "req-1")
