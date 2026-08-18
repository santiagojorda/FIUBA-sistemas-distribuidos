import os
import json
from common.logger import obtener_logger
import tempfile

logger = obtener_logger(__name__)

VOLUMEN_DIR = "/app/volumen"
TAMANIO_BATCH_PERSISTENCIA = 50
TAMANIO_BATCH_EMISION = 1000

class PersistidorEstado:
    """
    Persistidor de estado a disco sin bases de datos externos.
    Garantiza consistencia ante caídas mediante escritura atómica (write-and-replace).
    Cada worker/nodo tiene su propia carpeta mapeada a un volumen.
    """
    def __init__(self, node_name: str, base_dir: str = VOLUMEN_DIR):
        self.node_name = node_name
        self.directory = os.path.join(base_dir, node_name)
        self.filepath = os.path.join(self.directory, "estado.json")
        self._inicializar_directorio()

    def _inicializar_directorio(self):
        try:
            os.makedirs(self.directory, exist_ok=True)
        except Exception as e:
            logger.error(f"[Persistencia] Error creando directorio {self.directory}: {e}")

    def guardar(self, estado: dict) -> bool:
        """
        Guarda un diccionario de estado de forma atómica.
        Utiliza un archivo temporal en el mismo directorio y luego lo reemplaza.
        """
        temp_file = None
        try:
            # Creamos el archivo temporal en el mismo directorio para asegurar que esté en el mismo filesystem
            fd, temp_path = tempfile.mkstemp(dir=self.directory, prefix="temp_estado_", suffix=".json")
            temp_file = os.fdopen(fd, 'w', encoding='utf-8')
            
            json.dump(estado, temp_file, ensure_ascii=False)
            temp_file.flush()
            os.fsync(fd)  # Forzar el flush físico a disco
            temp_file.close()
            temp_file = None

            # Reemplazo atómico
            os.replace(temp_path, self.filepath)
            return True
        except Exception as e:
            logger.error(f"[Persistencia] Error guardando estado para {self.node_name}: {e}", exc_info=True)
            if temp_file:
                try:
                    temp_file.close()
                except:
                    pass
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
            return False

    def cargar(self) -> dict:
        """
        Carga el estado persistido. Si no existe, retorna un diccionario vacío.
        Lanza excepción si el archivo existe pero está corrupto.
        """
        if not os.path.exists(self.filepath):
            logger.debug(f"[Persistencia] No se encontró estado anterior para {self.node_name}. Iniciando limpio.")
            return {}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[Persistencia] Archivo de estado corrupto {self.filepath}: {e}")
            raise RuntimeError(f"Archivo de estado corrupto: {self.filepath}") from e
        except Exception as e:
            logger.error(f"[Persistencia] Error inesperado al leer archivo de estado {self.filepath}: {e}")
            raise

    def borrar(self) -> bool:
        """
        Borra el archivo de estado si existe.
        """
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
                return True
        except Exception as e:
            logger.error(f"[Persistencia] Error al borrar el archivo de estado {self.filepath}: {e}")
        return False
