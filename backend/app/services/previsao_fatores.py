"""
Fatores de calendário da previsão semanal (D112–D114), em funções puras.

Por que existem: o Ualker pediu que a previsão olhe "o mesmo período no ano
anterior, semana do mês, dia do mês, dia da semana, sazonalidade e
tendência". Dia da semana (a base) e tendência já existiam (D18, D19); aqui
entram os outros, como MULTIPLICADORES da previsão semanal (D114):

    previsão = base do dia da semana × tendência × ano × semana do mês × dia do mês × feriado

Todos saem da própria série da loja + produto, com o que se sabia até a
data de referência, a partir das "razões" de cada dia passado:

    razão(d) = venda(d) ÷ base do dia da semana de d (as 6 semanas antes de d)

Razão 1,10 = vendeu 10% acima do normal daquele dia da semana.

- Semana do mês (1ª a 5ª, pelo dia: 1–7, 8–14, ...): mediana das razões
  daquela semana ÷ mediana de todas. Capta, por exemplo, a semana do
  pagamento.
- Dia do mês: mediana das razões daquele dia ÷ mediana da semana do mês
  dele (só o que sobra além da semana, para não contar duas vezes).
- Ano anterior (D113, 364 dias antes = mesmo dia da semana): razões em
  volta do alvo um ano antes (±3 dias) ÷ razões dos 7 dias da tendência um
  ano antes. É a VARIAÇÃO sazonal entre hoje e o alvo; o nível de hoje já
  está na base × tendência.
- Feriado nacional (D112): o dia de feriado sai da base, da tendência e
  das razões (como um evento); no alvo que é feriado, o fator é a mediana
  das razões dos feriados passados. Se há evento cadastrado no alvo, o
  evento manda e o fator de feriado fica 1.

Proteções (D114): cada fator é puxado para 1 conforme o pouco dado
(peso n ÷ (n + K)) e limitado a uma faixa; a tendência já mede as razões
dos últimos 7 dias, que têm a sua própria semana e dia do mês, então os
fatores de mês são divididos pela média deles nesses 7 dias (senão a
semana do pagamento entraria duas vezes). Sem dado, o fator é 1.

Conta em float (são estimativas; o resultado volta como Decimal com 4
casas). Datas de feriado: nacionais fixos + móveis pela Páscoa (Carnaval,
Sexta-feira Santa, Corpus Christi); estaduais e municipais o gestor
cadastra como evento.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from statistics import median

DIAS_ANO = 364  # mesmo dia da semana (D113)
DIAS_RAZOES = 371  # um ano de razões + a semana da tendência de um ano antes
# Peso do dado: n ÷ (n + K). Limites: faixa do fator.
K_SEMANA_MES, LIMITE_SEMANA_MES = 30, (0.85, 1.15)
K_DIA_MES, LIMITE_DIA_MES = 30, (0.85, 1.15)
K_ANO, LIMITE_ANO = 6, (0.7, 1.3)
K_FERIADO, LIMITE_FERIADO = 3, (0.5, 1.5)
MINIMO_ANO = 3  # razões de cada lado (alvo e referência) para o fator do ano
# Variação de um ano antes menor que isto (em módulo) é tratada como ruído:
# fator do ano = 1. Só picos e vales claros passam (backtest de 2026-11-13).
ZONA_MORTA_ANO = 0.25
# Semana e dia do mês só com pelo menos ~6 meses de razões no último ano:
# com poucas semanas, o "efeito" de cada semana do mês é só ruído.
MINIMO_RAZOES_MES = 180

FATOR_ANO = "ano"
FATOR_SEMANA_MES = "semana_mes"
FATOR_DIA_MES = "dia_mes"
FATOR_FERIADO = "feriado"
TODOS_OS_FATORES = frozenset({FATOR_ANO, FATOR_SEMANA_MES, FATOR_DIA_MES, FATOR_FERIADO})
# Ligados por padrão (D114: cada um só fica se melhorar o teste no passado;
# ver docs/STATUS.md, log de 2026-11-13, e scripts/backtest_fatores.py).
FATORES_PADRAO = TODOS_OS_FATORES

UM = Decimal("1")


# ------------------------------------------------------------------ feriados

def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=64)
def feriados_nacionais(ano: int) -> dict[date, str]:
    p = pascoa(ano)
    fixos = {
        (1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho",
        (9, 7): "Independência", (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
        (11, 15): "Proclamação da República", (12, 25): "Natal",
    }
    dias = {date(ano, m, d): nome for (m, d), nome in fixos.items()}
    if ano >= 2024:  # Lei 14.759/2023
        dias[date(ano, 11, 20)] = "Consciência Negra"
    dias[p - timedelta(days=48)] = "Carnaval"
    dias[p - timedelta(days=47)] = "Carnaval"
    dias[p - timedelta(days=2)] = "Sexta-feira Santa"
    dias[p + timedelta(days=60)] = "Corpus Christi"
    return dias


def feriado(dia: date) -> str | None:
    return feriados_nacionais(dia.year).get(dia)


# ------------------------------------------------------------------ fatores

@dataclass(frozen=True)
class Fatores:
    ano: Decimal = UM
    semana_mes: Decimal = UM
    dia_mes: Decimal = UM
    feriado: Decimal = UM
    nome_feriado: str | None = None

    @property
    def produto(self) -> Decimal:
        return self.ano * self.semana_mes * self.dia_mes * self.feriado


def semana_do_mes(dia: date) -> int:
    return (dia.day - 1) // 7 + 1


def _encolher(bruto: float | None, n: int, k: int, limites: tuple[float, float]) -> Decimal:
    if bruto is None or n == 0:
        return UM
    peso = n / (n + k)
    valor = 1 + (bruto - 1) * peso
    valor = min(max(valor, limites[0]), limites[1])
    return Decimal(str(valor)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def razoes(serie: Mapping[date, float | None], ate: date, dias: int,
           base: Callable[[date], float | None]) -> dict[date, float]:
    """razão(d) = venda ÷ base, para os `dias` até `ate` com venda e base > 0 (feriado fica fora)."""
    saida = {}
    for k in range(dias):
        d = ate - timedelta(days=k)
        v = serie.get(d)
        if v is None or feriado(d):
            continue
        b = base(d)
        if b is not None and b > 0:
            saida[d] = v / b
    return saida


def calcular(
    razoes_dia: Mapping[date, float],
    razoes_feriado: list[float],
    data_referencia: date,
    data_alvo: date,
    dias_tendencia: list[date],
    tem_evento_no_alvo: bool,
    ligados: frozenset[str] = FATORES_PADRAO,
) -> Fatores:
    """
    Os fatores do `data_alvo` a partir das razões (já sem feriados e sem
    dias de evento) até `data_referencia`. `dias_tendencia` = os dias que
    entraram na tendência (para descontar a posição no mês deles).
    """
    um_ano = {d: r for d, r in razoes_dia.items() if d > data_referencia - timedelta(days=DIAS_ANO)}
    geral = median(um_ano.values()) if um_ano else None

    # Semana do mês.
    por_semana: dict[int, list[float]] = defaultdict(list)
    for d, r in um_ano.items():
        por_semana[semana_do_mes(d)].append(r)

    def f_semana(dia: date) -> Decimal:
        grupo = por_semana.get(semana_do_mes(dia), [])
        if not grupo or not geral:
            return UM
        return _encolher(median(grupo) / geral, len(grupo), K_SEMANA_MES, LIMITE_SEMANA_MES)

    # Dia do mês (o que sobra além da semana).
    por_dia: dict[int, list[float]] = defaultdict(list)
    for d, r in um_ano.items():
        por_dia[d.day].append(r)

    def f_dia(dia: date) -> Decimal:
        grupo, semana = por_dia.get(dia.day, []), por_semana.get(semana_do_mes(dia), [])
        if not grupo or not semana:
            return UM
        referencia = median(semana)
        if referencia <= 0:
            return UM
        return _encolher(median(grupo) / referencia, len(grupo), K_DIA_MES, LIMITE_DIA_MES)

    def descontar(f: Callable[[date], Decimal], alvo: Decimal) -> Decimal:
        """Alvo ÷ média do fator nos dias da tendência (a tendência já os contém)."""
        if not dias_tendencia:
            return alvo
        media = sum((f(d) for d in dias_tendencia), Decimal(0)) / len(dias_tendencia)
        return (alvo / media).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if media > 0 else alvo

    tem_ano_de_dado = len(um_ano) >= MINIMO_RAZOES_MES
    semana_mes = descontar(f_semana, f_semana(data_alvo)) if FATOR_SEMANA_MES in ligados and tem_ano_de_dado else UM
    dia_mes = descontar(f_dia, f_dia(data_alvo)) if FATOR_DIA_MES in ligados and tem_ano_de_dado else UM

    # Ano anterior: variação entre a semana da tendência e o alvo, um ano antes.
    ano = UM
    if FATOR_ANO in ligados:
        ancora = data_alvo - timedelta(days=DIAS_ANO)
        lado_alvo = [r for k in range(-3, 4) if (r := razoes_dia.get(ancora + timedelta(days=k))) is not None]
        lado_ref = [r for k in range(7)
                    if (r := razoes_dia.get(data_referencia - timedelta(days=DIAS_ANO + k))) is not None]
        if len(lado_alvo) >= MINIMO_ANO and len(lado_ref) >= MINIMO_ANO and median(lado_ref) > 0:
            n = min(len(lado_alvo), len(lado_ref))
            bruto = median(lado_alvo) / median(lado_ref)
            if abs(bruto - 1) >= ZONA_MORTA_ANO:
                ano = _encolher(bruto, n, K_ANO, LIMITE_ANO)

    # Feriado no alvo.
    nome = feriado(data_alvo)
    fator_feriado = UM
    if nome and FATOR_FERIADO in ligados and not tem_evento_no_alvo and razoes_feriado:
        fator_feriado = _encolher(median(razoes_feriado), len(razoes_feriado), K_FERIADO, LIMITE_FERIADO)

    return Fatores(ano=ano, semana_mes=semana_mes, dia_mes=dia_mes, feriado=fator_feriado, nome_feriado=nome)
