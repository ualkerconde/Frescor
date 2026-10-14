"""
Métricas de qualidade da previsão (Fase 3 / F6), em funções puras.

- WAPE (erro absoluto ponderado): Σ|real − previsto| ÷ Σ real. "Errou em
  média X% do volume". Pondera pelo volume: errar 1 unidade num produto que
  vende 1 pesa menos que errar 10 num que vende 100, ao contrário da média
  de erros percentuais, que explode em produto de venda baixa.
- Viés: Σ(previsto − real) ÷ Σ real. Positivo = tende a sobrar; negativo =
  tende a faltar. O WAPE não mostra o lado do erro; o viés mostra.
- Ingênuo: "vende o mesmo que no mesmo dia da semana passada". É a régua
  mínima: um motor que não vence o ingênuo não se paga.

Usado pelo teste no passado (`scripts/backtest_previsao.py`) e, na F8, pela
consulta de qualidade da tela de previsão.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Metricas:
    n: int
    soma_real: Decimal
    soma_erro_absoluto: Decimal
    soma_erro: Decimal

    @property
    def wape(self) -> Decimal | None:
        """None sem pares ou com venda real somando zero (não há volume para ponderar)."""
        return self.soma_erro_absoluto / self.soma_real if self.soma_real > 0 else None

    @property
    def vies(self) -> Decimal | None:
        return self.soma_erro / self.soma_real if self.soma_real > 0 else None


def medir(pares: Iterable[tuple[Decimal, Decimal]]) -> Metricas:
    """Métricas de uma lista de (real, previsto)."""
    n = 0
    soma_real = soma_abs = soma_erro = Decimal("0")
    for real, previsto in pares:
        n += 1
        soma_real += real
        soma_abs += abs(previsto - real)
        soma_erro += previsto - real
    return Metricas(n=n, soma_real=soma_real, soma_erro_absoluto=soma_abs, soma_erro=soma_erro)


def previsao_ingenua(serie: Mapping[date, Decimal | None], data_alvo: date) -> Decimal | None:
    """Venda do mesmo dia da semana anterior (None se o dia é faltante)."""
    return serie.get(data_alvo - timedelta(days=7))
