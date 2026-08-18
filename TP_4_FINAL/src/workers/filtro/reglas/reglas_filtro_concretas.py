from .regla_filtro_base import ReglaFiltro, ReglaComparacionBase

class ReglaIgual(ReglaComparacionBase):
    def _analizar_referencia(self, valor_crudo: str):
        return valor_crudo

    def _comparar(self, valor, valor_ref) -> bool:
        return valor == valor_ref

class ReglaMenor(ReglaComparacionBase):
    def _analizar_referencia(self, valor_crudo: str):
        try:
            return float(valor_crudo)
        except ValueError:
            return valor_crudo

    def _comparar(self, valor, valor_ref) -> bool:
        return valor < valor_ref

class ReglaEntre(ReglaFiltro):
    def _analizar_referencia(self, valor_crudo: str):
        limites = [lim.strip() for lim in valor_crudo.split(",")]
        if len(limites) != 2:
            raise ValueError(f"FILTER_VALUE incorrecto para between: {valor_crudo}")
        return limites

    def coincide(self, transaccion: dict) -> bool:
        if self.campo not in transaccion:
            return False
        valor = str(transaccion[self.campo])
        lim_inf, lim_sup = self.valor_ref
        largo_prefijo = min(len(lim_inf), len(lim_sup))
        return lim_inf <= valor[:largo_prefijo] <= lim_sup

class ReglaEn(ReglaFiltro):
    def _analizar_referencia(self, valor_crudo: str):
        return {opt.strip() for opt in valor_crudo.split(",")}

    def coincide(self, transaccion: dict) -> bool:
        if self.campo not in transaccion:
            return False
        valor = str(transaccion[self.campo])
        return valor in self.valor_ref
