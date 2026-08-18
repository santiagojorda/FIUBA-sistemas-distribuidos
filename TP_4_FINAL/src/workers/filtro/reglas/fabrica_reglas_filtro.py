from operadores import (
    OP_IGUAL,
    OP_MENOR,
    OP_ENTRE,
    OP_EN,
)
from .regla_filtro_base import ReglaFiltro
from .reglas_filtro_concretas import ReglaIgual, ReglaMenor, ReglaEntre, ReglaEn

class FabricaReglas:
    _registro = {
        OP_IGUAL: ReglaIgual,
        OP_MENOR: ReglaMenor,
        OP_ENTRE: ReglaEntre,
        OP_EN: ReglaEn,
    }

    _mapeo_operadores = {
        "igual": OP_IGUAL,
        "menor": OP_MENOR,
        "entre": OP_ENTRE,
        "en": OP_EN,
    }

    @classmethod
    def crear(cls, op_str: str, campo: str, valor_crudo: str) -> ReglaFiltro:
        op_normalizado = cls._mapeo_operadores.get(op_str.lower())
        if not op_normalizado:
            raise ValueError(f"Operador no soportado: {op_str}")
        clase_regla = cls._registro.get(op_normalizado)
        return clase_regla(campo, valor_crudo)
