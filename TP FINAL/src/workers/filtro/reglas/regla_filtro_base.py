from abc import ABC, abstractmethod

class ReglaFiltro(ABC):
    def __init__(self, campo: str, valor_crudo: str):
        self.campo = campo
        self.valor_ref = self._analizar_referencia(valor_crudo)

    @abstractmethod
    def _analizar_referencia(self, valor_crudo: str):
        pass

    @abstractmethod
    def coincide(self, transaccion: dict) -> bool:
        pass

class ReglaComparacionBase(ReglaFiltro, ABC):
    def coincide(self, transaccion: dict) -> bool:
        if self.campo not in transaccion:
            return False
        valor = transaccion[self.campo]
        if isinstance(self.valor_ref, float):
            try:
                valor = float(valor)
            except (ValueError, TypeError):
                valor = str(valor)
        else:
            valor = str(valor)
        return self._comparar(valor, self.valor_ref)

    @abstractmethod
    def _comparar(self, valor, valor_ref) -> bool:
        pass
