from common.crash_hook import CrashHook
from common import crash_points as CP

HOOK_PRE_FINISHED = "pre_finished"
HOOK_POST_FLUSH = "post_flush"

_hook = CrashHook()


def crear_hook_crash_pre_finished(prefijo_nodo, id_nodo):
    if not _is_enabled(CP.BEFORE_FINISHED_CONFIRMATION):
        return None

    def hook():
        _hook.verificar(CP.BEFORE_FINISHED_CONFIRMATION, f"pre-finished {prefijo_nodo}_{id_nodo}")

    return hook


def crear_hook_crash_despues_flush():
    if not _is_enabled(CP.AFTER_FLUSH):
        return None

    def hook():
        _hook.verificar(CP.AFTER_FLUSH, "post-flush")

    return hook


def crear_hook_crash_despues_persistir():
    if not _is_enabled(CP.AFTER_PERSIST):
        return None

    def hook():
        _hook.verificar(CP.AFTER_PERSIST, "post-persist")

    return hook


def crear_hook_crash_pre_barrera(prefijo_nodo: str):
    if not _is_enabled(CP.PRE_BARRERA):
        return None

    def hook():
        _hook.verificar(CP.PRE_BARRERA, f"pre-barrera {prefijo_nodo}")

    return hook


def _is_enabled(env_var):
    import os
    return os.environ.get(env_var) == "true"
