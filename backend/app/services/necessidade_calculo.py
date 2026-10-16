"""
Núcleo de cálculo da necessidade (Fase 4 / N3), em funções puras: recebe a
previsão gravada, o calendário, a contagem e o que está em trânsito de UMA
loja + produto e devolve quanto mandar produzir (ou distribuir), com os
componentes que explicam o número. Não lê banco nem relógio, para poder ser
testado com dados montados à mão; o `necessidade_service` (N4) monta as
entradas.

Método (docs/STATUS.md, "Fase 4 — plano"), para a data de produção D:

    chegada            = D + prazo de entrega da central (D32)
    cobertura          = da chegada até a véspera da próxima chegada (calendário),
                         limitada à validade do produto (D36)
    mínimo             = Σ previsão de cada dia da cobertura (doc §4.4)
    alvo               = mínimo × (1 + margem) (D34)
    estoque na chegada = contado + em trânsito − previsão dos dias entre a contagem
                         e a chegada, sem o que vence antes da chegada (D35, D45)
    necessidade        = max(0, alvo − estoque na chegada), arredondada (D37)

Por que cada peça:
- A cobertura soma a previsão dia a dia (não multiplica uma média), porque
  sábado vende diferente de terça. Ela para na validade: produzir para um
  dia em que o produto já venceu é sobra certa; o aviso pede para ajustar
  o calendário.
- A perda NÃO é somada (D35): produzir a perda esperada alimentaria a
  própria perda. Ela entra pela validade (estoque que vence antes da
  chegada não conta) e, na tela, como indicador.
- Contagem válida (D33, D44): só a feita desde o fechamento de D−1 menos
  2 h de folga, na hora local da loja; mais antiga conta 0, com aviso (sem
  registro de entrega, não dá para atualizar uma contagem velha).
- Projeção até a chegada (D45): com prazo 0 não há dia entre a contagem e a
  chegada. Com prazo 1, o que está na loja e o que chega em D são vendidos
  em D; só a sobra chega à cobertura que começa em D+1. O trânsito entra
  DENTRO da projeção (ver a nota da D45): fora dela, um lote vendido em D
  seria descontado de novo.
- Consumo na projeção em ordem de vencimento (o que vence antes sai antes,
  como na prateleira de perecível); ao fim de cada dia sai o que venceu.

Validade (`dias_validade`, "dias após a fabricação"): o produto fabricado
em F vale até F + validade − 1. A produção da ordem é fabricada em D; um
lote em trânsito, em (entrega − prazo). O estoque contado não tem lote:
supõe-se o mais novo possível (entregue no dia da contagem, fabricado
`prazo` dias antes). É otimista; a idade real só com lote (fora do V1).
Sem validade cadastrada, nada vence.

Limitação conhecida: um lote que ainda vale na chegada conta inteiro, mesmo
que vença no meio da cobertura antes de ser todo vendido.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

# Identifica o método que gerou a necessidade; vai gravado em cada ordem.
# Mudou uma regra da necessidade (cobertura, contagem, margem, projeção,
# arredondamento, filtros do necessidade_service), muda a versão.
# n1 (2026-10-15): D32-D53.
VERSAO_METODO_NECESSIDADE = "2026.10-n1"

# Margem (D34): sem margem no produto, 10%; produto com pouco histórico
# (cold start), pelo menos 20% (doc §4.2: em lançamento, falta é pior que
# sobra). Calibrar na Fase 7.
MARGEM_PADRAO = Decimal("10")
MARGEM_POUCO_HISTORICO = Decimal("20")
# Contagem válida (D44): desde o fechamento de D−1 menos esta folga.
FOLGA_CONTAGEM = timedelta(hours=2)
# Fuso da loja (D44): não há campo de fuso no banco; vale o padrão.
FUSO_PADRAO = "America/Sao_Paulo"
HORARIO_FECHAMENTO_PADRAO = time(21, 0)
# Arredondamento (D37): UN para cima no inteiro; KG para cima em 0,1 kg.
PASSO_ARREDONDAMENTO = {"UN": Decimal("1"), "KG": Decimal("0.1")}

ORIGEM_MARGEM_PRODUTO = "produto"
ORIGEM_MARGEM_PADRAO = "padrao"
ORIGEM_MARGEM_POUCO_HISTORICO = "pouco_historico"

# Avisos da linha (a tela traduz para frases).
AVISO_SEM_CALENDARIO = "sem_calendario"  # D42
AVISO_SEM_PREVISAO = "sem_previsao"
AVISO_SEM_CONTAGEM = "sem_contagem"  # D33: nunca foi contado
AVISO_CONTAGEM_DESATUALIZADA = "contagem_desatualizada"  # D33/D44
AVISO_COBERTURA_MAIOR_QUE_VALIDADE = "cobertura_maior_que_validade"  # D36
AVISO_VALIDADE_MENOR_QUE_PRAZO = "validade_menor_que_prazo"  # chega já vencido
AVISO_ESTOQUE_ACIMA_DO_MAXIMO = "estoque_acima_do_maximo"

_UTC = timezone.utc


@dataclass(frozen=True)
class Contagem:
    """Última contagem da loja + produto (`estoque_atual`)."""

    quantidade: Decimal
    # Como o app grava (`datetime.utcnow`): UTC, sem fuso.
    atualizado_em_utc: datetime


@dataclass(frozen=True)
class LoteTransito:
    """Linha de ordem aprovada para a loja, ainda sem recebimento confirmado (D43)."""

    data_entrega: date
    quantidade: Decimal


@dataclass(frozen=True)
class EntradaNecessidade:
    data_producao: date
    prazo_entrega_dias: int
    # Dias da semana do calendário (0 = segunda ... 6 = domingo); vazio = sem calendário.
    dias_producao: frozenset[int]
    dias_validade: int | None
    margem_produto: Decimal | None
    unidade: str  # "UN" ou "KG"
    # Previsão gravada por dia; None ou ausente = sem previsão para o dia.
    previsoes: Mapping[date, Decimal | None]
    # Algum dia da cobertura com pouco histórico (cold start) -> margem maior.
    pouco_historico: bool
    contagem: Contagem | None
    transito: Sequence[LoteTransito] = ()
    horario_fechamento: time = HORARIO_FECHAMENTO_PADRAO
    fuso: str = FUSO_PADRAO


@dataclass(frozen=True)
class Cobertura:
    chegada: date
    proxima_producao: date
    # Dias que a produção cobre (já limitados à validade).
    dias: tuple[date, ...]
    # Quantos dias seriam sem o limite da validade.
    dias_sem_limite: int
    limitada_pela_validade: bool


@dataclass(frozen=True)
class SituacaoContagem:
    valida: bool
    # Hora local da contagem e o limite de validade (fechamento de D−1 − folga).
    momento_local: datetime
    limite_local: datetime


@dataclass(frozen=True)
class ResultadoNecessidade:
    """Necessidade de uma loja + produto e as peças que a explicam."""

    data_producao: date
    chegada: date | None
    dias_cobertura: tuple[date, ...]
    dias_cobertura_sem_limite: int
    # Dias vendidos entre a contagem e a chegada (D45); vazio com prazo 0.
    dias_ate_chegada: tuple[date, ...]
    minimo: Decimal | None
    margem: Decimal | None
    origem_margem: str | None
    alvo: Decimal | None
    estoque_contado: Decimal | None  # None = sem contagem
    contagem_valida: bool
    contagem_local: datetime | None
    limite_contagem_local: datetime | None
    # Estoque contado que entrou na projeção (0 se desatualizado ou ausente).
    estoque_considerado: Decimal
    transito_considerado: Decimal
    consumo_ate_chegada: Decimal
    # Sobra que vence antes de chegar à cobertura.
    vencido_ate_chegada: Decimal
    estoque_na_chegada: Decimal | None
    necessidade_bruta: Decimal | None
    # Arredondada (D37); None = o gestor precisa informar (aviso).
    necessidade: Decimal | None
    avisos: tuple[str, ...]


def produz_no_dia(dia: date, dias_producao: frozenset[int]) -> bool:
    return dia.weekday() in dias_producao


def proxima_producao(dia: date, dias_producao: frozenset[int]) -> date | None:
    """Próximo dia de produção depois de `dia` (no máximo 7 dias à frente)."""
    for k in range(1, 8):
        candidato = dia + timedelta(days=k)
        if candidato.weekday() in dias_producao:
            return candidato
    return None


def ultimo_dia_valido(fabricacao: date, dias_validade: int | None) -> date | None:
    """Último dia de venda de algo fabricado em `fabricacao`; None = não vence."""
    if dias_validade is None:
        return None
    return fabricacao + timedelta(days=dias_validade - 1)


def calcular_cobertura(
    data_producao: date, prazo_entrega_dias: int, dias_producao: frozenset[int], dias_validade: int | None
) -> Cobertura:
    if not produz_no_dia(data_producao, dias_producao):
        raise ValueError(f"{data_producao} não é dia de produção do produto")
    proxima = proxima_producao(data_producao, dias_producao)
    chegada = data_producao + timedelta(days=prazo_entrega_dias)
    dias_sem_limite = (proxima - data_producao).days
    todos = [chegada + timedelta(days=k) for k in range(dias_sem_limite)]
    limite = ultimo_dia_valido(data_producao, dias_validade)
    dias = tuple(d for d in todos if limite is None or d <= limite)
    return Cobertura(
        chegada=chegada,
        proxima_producao=proxima,
        dias=dias,
        dias_sem_limite=dias_sem_limite,
        limitada_pela_validade=len(dias) < dias_sem_limite,
    )


def avaliar_contagem(
    atualizado_em_utc: datetime, data_producao: date, horario_fechamento: time, fuso: str
) -> SituacaoContagem:
    """D33/D44: válida se feita desde o fechamento de D−1 menos a folga, na hora local."""
    zona = ZoneInfo(fuso)
    momento = atualizado_em_utc.replace(tzinfo=_UTC).astimezone(zona)
    fechamento = datetime.combine(data_producao - timedelta(days=1), horario_fechamento, tzinfo=zona)
    limite = fechamento - FOLGA_CONTAGEM
    return SituacaoContagem(valida=momento >= limite, momento_local=momento, limite_local=limite)


def margem_aplicada(margem_produto: Decimal | None, pouco_historico: bool) -> tuple[Decimal, str]:
    """D34. Com pouco histórico vale a maior entre a do produto (ou a padrão) e 20%."""
    base, origem = (
        (margem_produto, ORIGEM_MARGEM_PRODUTO) if margem_produto is not None
        else (MARGEM_PADRAO, ORIGEM_MARGEM_PADRAO)
    )
    if pouco_historico and base < MARGEM_POUCO_HISTORICO:
        return MARGEM_POUCO_HISTORICO, ORIGEM_MARGEM_POUCO_HISTORICO
    return base, origem


def arredondar(valor: Decimal, unidade: str) -> Decimal:
    """D37: para cima, no inteiro (UN) ou em 0,1 kg (KG)."""
    passo = PASSO_ARREDONDAMENTO[unidade]
    return (valor / passo).to_integral_value(rounding=ROUND_CEILING) * passo


def projetar_estoque(
    lotes: Sequence[tuple[Decimal, date | None, date | None]],
    dias_ate_chegada: Sequence[date],
    previsoes: Mapping[date, Decimal],
    chegada: date,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    D45: estoque que sobra na chegada. `lotes` = (quantidade, dia em que fica
    disponível ou None se já está na loja, último dia válido ou None).
    Devolve (estoque na chegada, consumido, vencido).
    """
    pendentes = [list(lote) for lote in lotes]
    na_loja: list[list] = []
    consumido = Decimal(0)
    vencido = Decimal(0)

    def receber(ate: date) -> None:
        for lote in list(pendentes):
            if lote[1] is None or lote[1] <= ate:
                na_loja.append(lote)
                pendentes.remove(lote)

    def descartar_vencidos(antes_de: date) -> Decimal:
        total = Decimal(0)
        for lote in list(na_loja):
            if lote[2] is not None and lote[2] < antes_de:
                total += lote[0]
                na_loja.remove(lote)
        return total

    for dia in dias_ate_chegada:
        receber(dia)
        vencido += descartar_vencidos(dia)
        demanda = previsoes[dia]
        # O que vence antes sai antes (sem validade = por último).
        for lote in sorted(na_loja, key=lambda l: (l[2] is None, l[2] or date.max)):
            usado = min(lote[0], demanda)
            lote[0] -= usado
            demanda -= usado
            consumido += usado
        na_loja[:] = [l for l in na_loja if l[0] > 0]
    receber(chegada - timedelta(days=1))
    vencido += descartar_vencidos(chegada)
    return sum((l[0] for l in na_loja), Decimal(0)), consumido, vencido


def calcular_necessidade(e: EntradaNecessidade) -> ResultadoNecessidade:
    avisos: list[str] = []
    # Campos do resultado, preenchidos à medida que o cálculo avança (uma
    # saída antecipada devolve o que já se sabe, com o aviso do motivo).
    campos = dict(
        data_producao=e.data_producao, chegada=None, dias_cobertura=(), dias_cobertura_sem_limite=0,
        dias_ate_chegada=(), minimo=None, margem=None, origem_margem=None, alvo=None,
        estoque_contado=e.contagem.quantidade if e.contagem else None, contagem_valida=False,
        contagem_local=None, limite_contagem_local=None, estoque_considerado=Decimal(0),
        transito_considerado=Decimal(0), consumo_ate_chegada=Decimal(0), vencido_ate_chegada=Decimal(0),
        estoque_na_chegada=None, necessidade_bruta=None, necessidade=None,
    )
    if not e.dias_producao:
        return ResultadoNecessidade(**campos, avisos=(AVISO_SEM_CALENDARIO,))

    cob = calcular_cobertura(e.data_producao, e.prazo_entrega_dias, e.dias_producao, e.dias_validade)
    dias_ate_chegada = tuple(e.data_producao + timedelta(days=k) for k in range(e.prazo_entrega_dias))
    campos.update(chegada=cob.chegada, dias_cobertura=cob.dias, dias_cobertura_sem_limite=cob.dias_sem_limite,
                 dias_ate_chegada=dias_ate_chegada)
    if cob.limitada_pela_validade:
        avisos.append(AVISO_COBERTURA_MAIOR_QUE_VALIDADE)
    if not cob.dias:
        avisos.append(AVISO_VALIDADE_MENOR_QUE_PRAZO)
        return ResultadoNecessidade(**campos, avisos=tuple(avisos))

    # Contagem (D33, D44).
    estoque_considerado = Decimal(0)
    lotes: list[tuple[Decimal, date | None, date | None]] = []
    if e.contagem is None:
        avisos.append(AVISO_SEM_CONTAGEM)
    else:
        situacao = avaliar_contagem(e.contagem.atualizado_em_utc, e.data_producao, e.horario_fechamento, e.fuso)
        campos.update(contagem_valida=situacao.valida, contagem_local=situacao.momento_local,
                     limite_contagem_local=situacao.limite_local)
        if situacao.valida:
            estoque_considerado = e.contagem.quantidade
            fabricacao = situacao.momento_local.date() - timedelta(days=e.prazo_entrega_dias)
            lotes.append((estoque_considerado, None, ultimo_dia_valido(fabricacao, e.dias_validade)))
        else:
            avisos.append(AVISO_CONTAGEM_DESATUALIZADA)

    # Trânsito (D43): só o que chega entre a contagem (fim de D−1) e a chegada.
    transito_considerado = Decimal(0)
    for lote in e.transito:
        if e.data_producao <= lote.data_entrega < cob.chegada:
            transito_considerado += lote.quantidade
            fabricacao = lote.data_entrega - timedelta(days=e.prazo_entrega_dias)
            lotes.append((lote.quantidade, lote.data_entrega, ultimo_dia_valido(fabricacao, e.dias_validade)))
    campos.update(estoque_considerado=estoque_considerado, transito_considerado=transito_considerado)

    dias_com_previsao = dias_ate_chegada + cob.dias
    if any(e.previsoes.get(d) is None for d in dias_com_previsao):
        avisos.append(AVISO_SEM_PREVISAO)
        return ResultadoNecessidade(**campos, avisos=tuple(avisos))

    minimo = sum((e.previsoes[d] for d in cob.dias), Decimal(0))
    margem, origem_margem = margem_aplicada(e.margem_produto, e.pouco_historico)
    alvo = minimo * (1 + margem / 100)
    estoque_na_chegada, consumido, vencido = projetar_estoque(lotes, dias_ate_chegada, e.previsoes, cob.chegada)
    if estoque_na_chegada > alvo:
        avisos.append(AVISO_ESTOQUE_ACIMA_DO_MAXIMO)
    bruta = max(Decimal(0), alvo - estoque_na_chegada)
    campos.update(minimo=minimo, margem=margem, origem_margem=origem_margem, alvo=alvo,
                 consumo_ate_chegada=consumido, vencido_ate_chegada=vencido,
                 estoque_na_chegada=estoque_na_chegada, necessidade_bruta=bruta,
                 necessidade=arredondar(bruta, e.unidade))
    return ResultadoNecessidade(**campos, avisos=tuple(avisos))
