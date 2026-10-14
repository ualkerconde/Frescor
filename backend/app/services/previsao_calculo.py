"""
Núcleo de cálculo do motor de previsão (Fase 3 / F2), em funções puras:
recebe a série diária (de `serie_vendas_service`) e devolve a previsão com
os componentes que a explicam. Não lê banco nem relógio, para poder ser
testado com séries montadas à mão e reusado no teste no passado (F6).

Método (docs/STATUS.md, "Fase 3 — plano"):
- Base (D18): média das vendas do mesmo dia da semana nas últimas 6
  semanas conhecidas. Captura o padrão semanal (sábado vende mais que
  segunda) sem precisar de fatores configurados.
- Tendência (D19): soma do real dos últimos 7 dias ÷ soma da base desses
  mesmos dias, limitada a 0,7–1,3. Corrige a base quando o movimento
  mudou nas últimas semanas. O limite impede que uma semana atípica
  dobre ou zere a produção; com menos de 5 dos 7 dias comparáveis, o
  fator fica 1 (pouco dado para afirmar tendência).
- Previsão = base × tendência. Sem arredondamento (D21): arredondar é
  decisão da produção (Fase 4), não da previsão.

Dia faltante (`None`, D17) fica fora da média e da tendência. Dia ausente
do dicionário vale como faltante.

Fora deste passo: eventos (F3), produto/loja novos sem histórico (F4) e
produtos sazonais (F5). Sem nenhum dia na base, a previsão sai `None` e
o F4 decide o que fazer.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

JANELA_BASE_SEMANAS = 6  # D18
DIAS_TENDENCIA = 7  # D19
MINIMO_DIAS_TENDENCIA = 5  # D19
TENDENCIA_MINIMA = Decimal("0.7")  # D19
TENDENCIA_MAXIMA = Decimal("1.3")  # D19

Serie = Mapping[date, Decimal | None]


@dataclass(frozen=True)
class ComponentesPrevisao:
    """Previsão de um dia e as peças que a compõem (para a tela explicar o número)."""

    data_alvo: date
    # Média do mesmo dia da semana; None se nenhuma das 6 semanas tem dado.
    base: Decimal | None
    # Quantas das 6 semanas entraram na base (as outras eram faltantes).
    semanas_na_base: int
    # Fator aplicado, já limitado a 0,7–1,3 (1 quando não há dado suficiente).
    tendencia: Decimal
    # Real ÷ base antes do limite; None quando não houve dado para calcular.
    tendencia_bruta: Decimal | None
    # Quantos dos últimos 7 dias tinham real e base para comparar.
    dias_na_tendencia: int
    # base × tendência; None quando não há base.
    previsao: Decimal | None


def base_dia_semana(serie: Serie, data_referencia: date, data_alvo: date) -> tuple[Decimal | None, int]:
    """
    Média dos últimos `JANELA_BASE_SEMANAS` dias com o mesmo dia da semana
    de `data_alvo`, só até `data_referencia` (inclusive). Devolve (média,
    quantos dias entraram).
    """
    # Último dia com o mesmo dia da semana do alvo que já é conhecido.
    recuo = (data_alvo - data_referencia).days % 7
    ultimo = data_referencia - timedelta(days=(7 - recuo) % 7)
    valores = [
        v
        for k in range(JANELA_BASE_SEMANAS)
        if (v := serie.get(ultimo - timedelta(weeks=k))) is not None
    ]
    if not valores:
        return None, 0
    return sum(valores, Decimal("0")) / len(valores), len(valores)


def tendencia(serie: Serie, data_referencia: date) -> tuple[Decimal, Decimal | None, int]:
    """
    Fator de tendência dos últimos `DIAS_TENDENCIA` dias até `data_referencia`.
    Devolve (fator limitado, fator bruto, dias comparados).

    Cada dia entra só se tem o real e a base dele (calculada com as semanas
    anteriores a ele). Soma contra soma, e não média de razões: um dia de
    venda baixa não vira uma razão enorme.
    """
    soma_real = Decimal("0")
    soma_base = Decimal("0")
    dias = 0
    for k in range(DIAS_TENDENCIA):
        dia = data_referencia - timedelta(days=k)
        real = serie.get(dia)
        if real is None:
            continue
        base, _ = base_dia_semana(serie, dia - timedelta(days=1), dia)
        if base is None:
            continue
        soma_real += real
        soma_base += base
        dias += 1
    if dias < MINIMO_DIAS_TENDENCIA or soma_base == 0:
        return Decimal("1"), None, dias
    bruta = soma_real / soma_base
    return min(max(bruta, TENDENCIA_MINIMA), TENDENCIA_MAXIMA), bruta, dias


def prever(serie: Serie, data_referencia: date, data_alvo: date) -> ComponentesPrevisao:
    """
    Previsão de venda para `data_alvo`, usando só o que se sabe até
    `data_referencia` (normalmente ontem). Dados da série depois de
    `data_referencia` são ignorados.
    """
    if data_alvo <= data_referencia:
        raise ValueError("A data prevista tem de ser depois da data de referência.")
    conhecida = {dia: valor for dia, valor in serie.items() if dia <= data_referencia}
    base, semanas = base_dia_semana(conhecida, data_referencia, data_alvo)
    fator, bruta, dias = tendencia(conhecida, data_referencia)
    return ComponentesPrevisao(
        data_alvo=data_alvo,
        base=base,
        semanas_na_base=semanas,
        tendencia=fator,
        tendencia_bruta=bruta,
        dias_na_tendencia=dias,
        previsao=None if base is None else base * fator,
    )
