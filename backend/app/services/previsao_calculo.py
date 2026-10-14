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

Eventos (F3, doc §4.3): dia coberto por evento também fica fora da base e
da tendência (venda atípica não pode virar "normal" nas semanas
seguintes). O ajuste do evento no dia previsto é aplicado por
`aplicar_eventos`, DEPOIS do cold start (F4), sobre a previsão já
combinada.

Cold start (F4, doc §4.2 e D20): `peso_historico_proprio` e
`combinar_cold_start` misturam a previsão própria com um proxy enquanto o
produto (ou a loja) tem menos de 6 semanas de histórico. A escolha do
proxy precisa de outras lojas e produtos, por isso fica no
`previsao_service`.

Fora deste passo: produtos sazonais (F5). Sem nenhum dia na base, a
previsão própria sai `None`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models.evento import TipoAjuste

JANELA_BASE_SEMANAS = 6  # D18
DIAS_TENDENCIA = 7  # D19
MINIMO_DIAS_TENDENCIA = 5  # D19
TENDENCIA_MINIMA = Decimal("0.7")  # D19
TENDENCIA_MAXIMA = Decimal("1.3")  # D19
# Quantos dias antes da referência a série precisa ter: a base de cada um
# dos 7 dias da tendência olha 6 semanas para trás.
DIAS_HISTORICO_NECESSARIOS = 7 * JANELA_BASE_SEMANAS + DIAS_TENDENCIA - 1
# Cold start (doc §4.2, D20): o peso do histórico próprio vai de 0% (1ª
# semana) a 100% depois de 6 semanas completas.
SEMANAS_COLD_START = 6

Serie = Mapping[date, Decimal | None]


@dataclass(frozen=True)
class EventoAplicavel:
    """Evento já filtrado para uma loja; o produto é conferido por `vale_para_produto`."""

    id: int
    nome: str
    data_inicio: date
    data_fim: date
    tipo_ajuste: TipoAjuste
    valor_ajuste: Decimal
    # None = todos os produtos do negócio.
    produto_ids: frozenset[int] | None

    def vale_para_produto(self, produto_id: int) -> bool:
        return self.produto_ids is None or produto_id in self.produto_ids

    def cobre(self, dia: date) -> bool:
        return self.data_inicio <= dia <= self.data_fim


def eventos_do_produto(eventos: Sequence[EventoAplicavel], produto_id: int) -> list[EventoAplicavel]:
    return [e for e in eventos if e.vale_para_produto(produto_id)]


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


def prever(
    serie: Serie, data_referencia: date, data_alvo: date, eventos: Sequence[EventoAplicavel] = ()
) -> ComponentesPrevisao:
    """
    Previsão de venda para `data_alvo`, usando só o que se sabe até
    `data_referencia` (normalmente ontem). Dados da série depois de
    `data_referencia` são ignorados.

    `eventos` são os do produto nesta loja: os dias que eles cobrem saem
    da base e da tendência. O ajuste no alvo NÃO é aplicado aqui (ver
    `aplicar_eventos`).
    """
    if data_alvo <= data_referencia:
        raise ValueError("A data prevista tem de ser depois da data de referência.")
    conhecida = {
        dia: None if any(e.cobre(dia) for e in eventos) else valor
        for dia, valor in serie.items()
        if dia <= data_referencia
    }
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


def peso_historico_proprio(inicio_historico: date | None, data_referencia: date) -> Decimal:
    """
    Peso do histórico próprio no cold start: semanas completas de histórico
    até a referência ÷ 6, limitado a 1. Sem histórico (ou começando depois
    da referência), peso 0.

    Ex.: 1 a 6 dias -> 0; 7 a 13 dias -> 1/6; 42 dias ou mais -> 1.
    """
    if inicio_historico is None or inicio_historico > data_referencia:
        return Decimal("0")
    semanas = ((data_referencia - inicio_historico).days + 1) // 7
    return min(Decimal("1"), Decimal(semanas) / SEMANAS_COLD_START)


def combinar_cold_start(propria: Decimal | None, peso: Decimal, proxy: Decimal | None) -> Decimal | None:
    """
    previsão = peso × própria + (1 − peso) × proxy (doc §4.2).

    Falta de uma das partes: usa a outra inteira (sem proxy, a própria é
    melhor que nada; sem própria, por exemplo nenhum dia ainda no mesmo
    dia da semana, o proxy). Sem nenhuma das duas: None.
    """
    if peso >= 1 or proxy is None:
        return propria
    if propria is None:
        return proxy
    return peso * propria + (1 - peso) * proxy


def aplicar_eventos(
    previsao: Decimal | None, eventos: Sequence[EventoAplicavel], data_alvo: date
) -> tuple[Decimal | None, tuple[EventoAplicavel, ...]]:
    """
    Ajuste dos eventos do produto que cobrem `data_alvo` (proposta D26).
    Devolve (previsão ajustada, eventos que mexeram no número).

    - Valor fixo: é a previsão do dia para a loja + produto; substitui a
      previsão normal (vale mesmo sem histórico). Mais de um valor fixo
      no mesmo dia: vale o cadastrado por último (maior id).
    - Multiplicador: multiplica a previsão normal; vários se multiplicam.
      Sem previsão normal, não há o que multiplicar (continua None).
    - Valor fixo e multiplicador no mesmo dia: vale o valor fixo.
    """
    no_dia = [e for e in eventos if e.cobre(data_alvo)]
    fixos = [e for e in no_dia if e.tipo_ajuste == TipoAjuste.VALOR_FIXO]
    if fixos:
        ultimo = max(fixos, key=lambda e: e.id)
        return ultimo.valor_ajuste, (ultimo,)
    multiplicadores = tuple(sorted((e for e in no_dia if e.tipo_ajuste == TipoAjuste.MULTIPLICADOR),
                                   key=lambda e: e.id))
    if not multiplicadores or previsao is None:
        return previsao, multiplicadores
    fator = Decimal("1")
    for e in multiplicadores:
        fator *= e.valor_ajuste
    return previsao * fator, multiplicadores
