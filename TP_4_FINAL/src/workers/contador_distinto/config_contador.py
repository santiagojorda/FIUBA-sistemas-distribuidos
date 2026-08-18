import os
from operadores_contador import OP_IGUAL


def _parsear_campos(nombre_env: str, default: str = "") -> list[str]:
    raw = os.environ.get(nombre_env, default)
    return [f.strip() for f in raw.split(",") if f.strip()]


class ConfigContador:
    """Lee y expone toda la configuración del worker desde variables de entorno."""

    def __init__(self):
        self.campos_grupo = _parsear_campos("GROUP_FIELDS")
        self.campos_valor = _parsear_campos("VALUE_FIELDS")
        self.campos_salida_grupo = _parsear_campos("GROUP_OUTPUT_FIELDS") or self.campos_grupo
        self.campos_salida_valor = _parsear_campos("VALUE_OUTPUT_FIELDS") or self.campos_valor
        self.conteo_esperado = int(os.environ.get("EXPECTED_COUNT", "5"))
        self.operador = os.environ.get("COMPARISON_OPERATOR", OP_IGUAL).lower()
        self.modo_emision = os.environ.get("EMIT_MODE", "aggregate").lower()
        self.campo_conteo = os.environ.get("COUNT_OUTPUT_FIELD", "Amount Transactions")
