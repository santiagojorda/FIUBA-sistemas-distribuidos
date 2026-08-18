import os
from common.logger import obtener_logger

logger = obtener_logger(__name__)

VOLUMEN_DIR = os.getenv("CRASH_HOOK_VOLUMEN", "/app/volumen")


class CrashHook:
    def __init__(self, volumen_dir=VOLUMEN_DIR):
        self._volumen_dir = volumen_dir

    def verificar(self, env_var, descripcion=""):
        if os.environ.get(env_var) != "true":
            return
        bandera = os.path.join(self._volumen_dir, f"crash_{env_var}_done")
        if os.path.exists(bandera):
            return
        os.makedirs(os.path.dirname(bandera), exist_ok=True)
        with open(bandera, "w") as f:
            f.write("1")
        logger.warning(f"CRASH HOOK: {env_var} ({descripcion})")
        os._exit(1)
