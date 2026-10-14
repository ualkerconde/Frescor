"""
Núcleo de cálculo do motor de previsão (Fase 3 / F2), em funções puras:
recebe a série diária (de `serie_vendas_service`) e devolve a previsão com
os componentes que a explicam. Não lê banco nem relógio, para poder ser
testado com séries montadas à mão e reusado no teste no passado (F6).

Método (docs/STATUS.md, "Fase 3 — plano"):
- Base (D18 e D25): mediana das vendas do mesmo dia da semana nas
  últimas 6 semanas conhecidas. Captura o padrão semanal (sábado vende
  mais que segunda) sem precisar de fatores configurados; a mediana não
  se deixa levar por um dia de pico (promoção não cadastrada, erro de
  digitação), ao contrário da média.
- Tendência (D19 e D31): mediana das razões diárias real ÷ base dos
  últimos 7 dias, limitada a 0,7–1,3. Corrige a base quando o movimento
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

Sazonal (F5, doc §4.1): `prever_sazonal` usa o mesmo período do ano
anterior; `vigente` diz se o produto está à venda num dia (D30).

Sem nenhum dia na base, a previsão própria sai `None`.
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
# Sazonal (F5, doc §4.1): o "mesmo dia" do ano anterior fica 364 dias antes
# (52 semanas: mesmo dia da semana); a base usa esse dia e 2 semanas antes
# e depois dele.
DIAS_ANO_SAZONAL = 364
SEMANAS_AO_REDOR_SAZONAL = 2
METODO_SEMANAL = "semanal"
METODO_SAZONAL = "sazonal"
# Estatística da base. D25 (decidida em 2026-10-14): MEDIANA. No teste no
# passado (F6), as três empatam em dado limpo; com picos de venda, a média
# piora até perder do ingênuo e a mediana segue a melhor (docs/STATUS.md).
# As outras duas ficam disponíveis para o backtest comparar.
ESTATISTICA_MEDIA = "media"
ESTATISTICA_MEDIANA = "mediana"
ESTATISTICA_MEDIA_APARADA = "media_aparada"
ESTATISTICAS = (ESTATISTICA_MEDIA, ESTATISTICA_MEDIANA, ESTATISTICA_MEDIA_APARADA)
ESTATISTICA_PADRAO = ESTATISTICA_MEDIANA
# Como juntar os últimos 7 dias na tendência. D31 (decidida em 2026-10-14):
# mediana das razões diárias real ÷ base. No backtest, custa 0,2–0,4 ponto
# de WAPE em dado limpo e tira quase todo o efeito de picos (viés de +6,6%
# para +0,8% com 3% dos dias ×4). A soma (D19 original) fica para comparar.
TENDENCIA_SOMA = "soma"
TENDENCIA_MEDIANA = "mediana"
TENDENCIAS = (TENDENCIA_SOMA, TENDENCIA_MEDIANA)
TENDENCIA_PADRAO = TENDENCIA_MEDIANA

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
    # "semanal" (últimas 6 semanas) ou "sazonal" (mesmo período do ano anterior).
    metodo: str = METODO_SEMANAL


def resumir(valores: list[Decimal], estatistica: str = ESTATISTICA_PADRAO) -> Decimal:
    """
    Valor típico de uma lista (não vazia) de vendas, conforme a D25:
    - mediana (padrão): valor do meio (média dos dois do meio, se par);
    - media: média simples;
    - media_aparada: com 4 valores ou mais, tira o maior e o menor e faz a
      média do resto; com menos, média simples.
    """
    if estatistica == ESTATISTICA_MEDIANA:
        ordenados = sorted(valores)
        meio = len(ordenados) // 2
        return ordenados[meio] if len(ordenados) % 2 else (ordenados[meio - 1] + ordenados[meio]) / 2
    if estatistica == ESTATISTICA_MEDIA_APARADA and len(valores) >= 4:
        valores = sorted(valores)[1:-1]
    elif estatistica not in (ESTATISTICA_MEDIA, ESTATISTICA_MEDIA_APARADA):
        raise ValueError(f"Estatística desconhecida: {estatistica}")
    return sum(valores, Decimal("0")) / len(valores)


def base_dia_semana(
    serie: Serie, data_referencia: date, data_alvo: date, estatistica: str = ESTATISTICA_PADRAO
) -> tuple[Decimal | None, int]:
    """
    Valor típico (mediana, por padrão; D25) dos últimos `JANELA_BASE_SEMANAS`
    dias com o mesmo dia da semana de `data_alvo`, só até `data_referencia`
    (inclusive). Devolve (valor, quantos dias entraram).
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
    return resumir(valores, estatistica), len(valores)


def fator_tendencia(
    pares: list[tuple[Decimal, Decimal]], metodo: str = TENDENCIA_PADRAO
) -> tuple[Decimal, Decimal | None]:
    """
    Fator de tendência a partir de pares (real, referência) dos últimos dias
    (referência = base do dia, ou o mesmo dia do ano anterior no sazonal).
    Devolve (fator limitado a 0,7–1,3, fator bruto). Com menos de 5 pares
    (D19), ou sem referência para dividir, o fator é 1 e o bruto None.

    - mediana (padrão, D31): mediana das razões diárias real ÷ referência
      (dias com referência zero ficam fora). Um pico vira só uma razão alta,
      que a mediana ignora. Custo: uma mudança real que só aparece em 2 ou
      3 dos 7 dias demora mais a entrar.
    - soma (D19 original, para comparação): Σ real ÷ Σ referência. Um pico
      entra inteiro na soma.
    """
    if len(pares) < MINIMO_DIAS_TENDENCIA:
        return Decimal("1"), None
    if metodo == TENDENCIA_SOMA:
        soma_referencia = sum((b for _, b in pares), Decimal("0"))
        if soma_referencia == 0:
            return Decimal("1"), None
        bruta = sum((r for r, _ in pares), Decimal("0")) / soma_referencia
    elif metodo == TENDENCIA_MEDIANA:
        razoes = [r / b for r, b in pares if b > 0]
        if len(razoes) < MINIMO_DIAS_TENDENCIA:
            return Decimal("1"), None
        bruta = resumir(razoes, ESTATISTICA_MEDIANA)
    else:
        raise ValueError(f"Método de tendência desconhecido: {metodo}")
    return min(max(bruta, TENDENCIA_MINIMA), TENDENCIA_MAXIMA), bruta


def tendencia(
    serie: Serie,
    data_referencia: date,
    estatistica: str = ESTATISTICA_PADRAO,
    metodo: str = TENDENCIA_PADRAO,
) -> tuple[Decimal, Decimal | None, int]:
    """
    Fator de tendência dos últimos `DIAS_TENDENCIA` dias até `data_referencia`.
    Devolve (fator limitado, fator bruto, dias comparados).

    Cada dia entra só se tem o real e a base dele (calculada com as semanas
    anteriores a ele). O jeito de juntar os dias está em `fator_tendencia`.
    """
    pares = []
    for k in range(DIAS_TENDENCIA):
        dia = data_referencia - timedelta(days=k)
        real = serie.get(dia)
        if real is None:
            continue
        base, _ = base_dia_semana(serie, dia - timedelta(days=1), dia, estatistica)
        if base is None:
            continue
        pares.append((real, base))
    fator, bruta = fator_tendencia(pares, metodo)
    return fator, bruta, len(pares)


def prever(
    serie: Serie,
    data_referencia: date,
    data_alvo: date,
    eventos: Sequence[EventoAplicavel] = (),
    estatistica: str = ESTATISTICA_PADRAO,
    metodo_tendencia: str = TENDENCIA_PADRAO,
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
    base, semanas = base_dia_semana(conhecida, data_referencia, data_alvo, estatistica)
    fator, bruta, dias = tendencia(conhecida, data_referencia, estatistica, metodo_tendencia)
    return ComponentesPrevisao(
        data_alvo=data_alvo,
        base=base,
        semanas_na_base=semanas,
        tendencia=fator,
        tendencia_bruta=bruta,
        dias_na_tendencia=dias,
        previsao=None if base is None else base * fator,
    )


def vigente(dia: date, inicio: date | None, fim: date | None, recorrente: bool) -> bool:
    """
    O produto está à venda em `dia`? Sem datas: sempre. Vigência recorrente
    (sazonal) compara só dia e mês e pode virar o ano (ex.: 01/12 a 06/01).
    """
    if recorrente and inicio is not None and fim is not None:
        md, ini, fi = (dia.month, dia.day), (inicio.month, inicio.day), (fim.month, fim.day)
        return ini <= md <= fi if ini <= fi else (md >= ini or md <= fi)
    return (inicio is None or dia >= inicio) and (fim is None or dia <= fim)


def prever_sazonal(
    serie: Serie,
    data_referencia: date,
    data_alvo: date,
    eventos: Sequence[EventoAplicavel] = (),
    estatistica: str = ESTATISTICA_PADRAO,
    metodo_tendencia: str = TENDENCIA_PADRAO,
) -> ComponentesPrevisao | None:
    """
    Previsão de produto sazonal com temporada anterior (doc §4.1): a base é
    a média do mesmo dia da semana no mesmo período do ano anterior (o dia
    de 364 dias antes, e 2 semanas antes e depois dele); a tendência compara
    os últimos 7 dias com os mesmos 7 dias do ano anterior (limites e
    mínimo da D19). None quando não há dado do ano anterior (1ª temporada:
    o serviço segue pelo cold start).

    A série deve vir com os dias fora da vigência como faltantes (venda zero
    fora da temporada é ausência, não sazonalidade).
    """
    if data_alvo <= data_referencia:
        raise ValueError("A data prevista tem de ser depois da data de referência.")
    conhecida = {
        dia: None if any(e.cobre(dia) for e in eventos) else valor
        for dia, valor in serie.items()
        if dia <= data_referencia
    }
    ano = timedelta(days=DIAS_ANO_SAZONAL)
    ancora = data_alvo - ano
    valores = [
        v
        for k in range(-SEMANAS_AO_REDOR_SAZONAL, SEMANAS_AO_REDOR_SAZONAL + 1)
        if (v := conhecida.get(ancora + timedelta(weeks=k))) is not None
    ]
    if not valores:
        return None
    base = resumir(valores, estatistica)

    pares = []
    for k in range(DIAS_TENDENCIA):
        dia = data_referencia - timedelta(days=k)
        real, anterior = conhecida.get(dia), conhecida.get(dia - ano)
        if real is not None and anterior is not None:
            pares.append((real, anterior))
    fator, bruta = fator_tendencia(pares, metodo_tendencia)
    return ComponentesPrevisao(
        data_alvo=data_alvo,
        base=base,
        semanas_na_base=len(valores),
        tendencia=fator,
        tendencia_bruta=bruta,
        dias_na_tendencia=len(pares),
        previsao=base * fator,
        metodo=METODO_SAZONAL,
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
