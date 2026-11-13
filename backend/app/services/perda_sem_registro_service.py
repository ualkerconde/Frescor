"""
Perda sem registro e ruptura (D111, segunda parte), por loja, produto e dia.

Por que existe: o supermercado em geral não registra perda (análise de
07/11/2026). A perda lançada (D110) depende de a loja lembrar de lançar; o
que some sem ninguém anotar (descarte não lançado, furto, erro de contagem,
reaproveitamento) só aparece cruzando a contagem com o movimento do dia:

    esperado       = contagem do fechamento de ontem + recebido − vendido − perda lançada
    sem registro   = esperado − contagem do fechamento de hoje

Positivo: sumiu produto sem registro. Negativo: apareceu mais do que o
esperado (venda ou recebimento a menos no registro, ou contagem errada).
Mostra o tamanho do problema, não a causa. É só indicador: não entra na
previsão nem na necessidade (por isso não muda nenhuma VERSAO_METODO) e
não é gravado em `perdas_diarias` (a origem `inferida` somaria com a perda
lançada nas leituras de perda).

Ruptura: a contagem do fechamento deu zero e houve venda no dia. O produto
acabou; a venda daquele dia mostra o que havia, não o que se venderia.

Regras de cada parte (sempre filtrado pelo negócio e pelas lojas do gestor):
- Contagem do fechamento do dia D: o último lançamento do app com hora
  local entre o fechamento de D menos 2 h (a mesma folga da D44) e 12 h
  depois do fechamento (a contagem feita na manhã seguinte, antes de
  abrir, ainda é o fechamento de D). Vem dos snapshots da zeragem
  (`historico_contagens`) e da linha atual (`estoque_atual`), pela hora do
  lançamento (`contado_em`, migration 0028). Sem contagem nessa janela,
  o dia não tem balanço.
- Recebido em D: itens das entregas que saíram da central (`expedido_em`)
  com dia de entrega D; vale a quantidade recebida e, sem confirmação, a
  enviada (D89: chega no dia de entrega, antes da contagem do fechamento).
- Vendido e perda lançada de D: registros efetivos (D16). O balanço só sai
  se a loja tem alguma venda registrada no dia (senão a venda não chegou
  e o balanço acusaria tudo como perda); produto sem linha de venda nesse
  dia = vendeu zero.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.estoque_atual import EstoqueAtual
from app.models.historico_contagem import HistoricoContagem
from app.models.loja import Loja
from app.models.perda_diaria import PerdaDiaria
from app.models.romaneio import Romaneio
from app.models.romaneio_entrega import RomaneioEntrega
from app.models.romaneio_item import RomaneioItem
from app.models.venda_diaria import VendaDiaria
from app.services.necessidade_calculo import FOLGA_CONTAGEM, FUSO_PADRAO
from app.services.registros_efetivos import condicao_registro_efetivo

# Até quanto tempo depois do fechamento uma contagem ainda é "do fechamento" daquele dia.
JANELA_DEPOIS_DO_FECHAMENTO = timedelta(hours=12)

Celula = tuple[int, int, date]  # loja, produto, dia


@dataclass(frozen=True)
class Balanco:
    abertura: Decimal  # contagem do fechamento do dia anterior
    recebido: Decimal
    vendido: Decimal
    perda: Decimal
    fechamento: Decimal
    sem_registro: Decimal
    ruptura: bool


def balanco(abertura, recebido, vendido, perda, fechamento) -> Balanco:
    """A conta do dia (função pura)."""
    abertura, recebido, vendido, perda, fechamento = (
        Decimal(abertura), Decimal(recebido), Decimal(vendido), Decimal(perda), Decimal(fechamento)
    )
    esperado = abertura + recebido - vendido - perda
    return Balanco(abertura, recebido, vendido, perda, fechamento, esperado - fechamento,
                   ruptura=fechamento == 0 and vendido > 0)


def dia_do_fechamento(contado_em_utc: datetime, horario_fechamento: time, fuso: str = FUSO_PADRAO) -> date | None:
    """
    De que dia esta contagem é o fechamento: D se a hora local está entre o
    fechamento de D − 2 h e o fechamento de D + 12 h. Fora disso (contagem no
    meio do dia), None.
    """
    zona = ZoneInfo(fuso)
    local = contado_em_utc.replace(tzinfo=timezone.utc).astimezone(zona)
    for d in (local.date(), local.date() - timedelta(days=1)):
        fechamento = datetime.combine(d, horario_fechamento, tzinfo=zona)
        if fechamento - FOLGA_CONTAGEM <= local < fechamento + JANELA_DEPOIS_DO_FECHAMENTO:
            return d
    return None


def fechamentos(
    lancamentos: list[tuple[int, int, datetime, Decimal]],
    horarios: dict[int, time],
    fuso: str = FUSO_PADRAO,
) -> dict[Celula, Decimal]:
    """
    (loja, produto, contado_em UTC, valor) -> contagem do fechamento por
    célula (o lançamento mais tarde da janela vale). Função pura.
    """
    melhor: dict[Celula, tuple[datetime, Decimal]] = {}
    for loja_id, produto_id, contado_em, valor in lancamentos:
        if contado_em is None or loja_id not in horarios:
            continue
        dia = dia_do_fechamento(contado_em, horarios[loja_id], fuso)
        if dia is None:
            continue
        chave = (loja_id, produto_id, dia)
        if chave not in melhor or contado_em > melhor[chave][0]:
            melhor[chave] = (contado_em, Decimal(valor))
    return {c: v for c, (_, v) in melhor.items()}


def montar(
    inicio: date,
    fim: date,
    contagens: dict[Celula, Decimal],
    recebido: dict[Celula, Decimal],
    vendido: dict[Celula, Decimal],
    perda: dict[Celula, Decimal],
    lojas_com_venda: set[tuple[int, date]],
) -> dict[Celula, Balanco]:
    """Balanço de cada célula do período que tem as duas contagens e venda na loja (função pura)."""
    saida: dict[Celula, Balanco] = {}
    for (loja_id, produto_id, dia), fechamento in contagens.items():
        if not (inicio <= dia <= fim) or (loja_id, dia) not in lojas_com_venda:
            continue
        abertura = contagens.get((loja_id, produto_id, dia - timedelta(days=1)))
        if abertura is None:
            continue
        c = (loja_id, produto_id, dia)
        saida[c] = balanco(abertura, recebido.get(c, 0), vendido.get(c, 0), perda.get(c, 0), fechamento)
    return saida


# ------------------------------------------------------------------ leitura

def _lancamentos(db: Session, negocio_id: int, lojas: list[int], inicio: date, fim: date, produto_id: int | None):
    # Margem de 2 dias nas pontas: o filtro fino (janela do fechamento, hora local) é feito em `fechamentos`.
    de = datetime.combine(inicio - timedelta(days=2), time.min)
    ate = datetime.combine(fim + timedelta(days=2), time.min)
    saida = []
    for modelo in (HistoricoContagem, EstoqueAtual):
        q = db.query(modelo.loja_id, modelo.produto_id, modelo.contado_em, modelo.estoque_atual_calculado).filter(
            modelo.negocio_id == negocio_id, modelo.loja_id.in_(lojas), modelo.contado_em.isnot(None),
            modelo.contado_em >= de, modelo.contado_em < ate,
        )
        if produto_id is not None:
            q = q.filter(modelo.produto_id == produto_id)
        saida.extend(q.distinct().all())
    return saida


def _celulas(q) -> dict[Celula, Decimal]:
    saida: dict[Celula, Decimal] = defaultdict(Decimal)
    for loja_id, produto_id, dia, valor in q:
        if valor is not None:
            saida[(loja_id, produto_id, dia)] += Decimal(valor)
    return saida


def _diarios(db, modelo, negocio_id, lojas, inicio, fim, produto_id):
    q = db.query(modelo.loja_id, modelo.produto_id, modelo.data, func.sum(modelo.quantidade)).filter(
        modelo.negocio_id == negocio_id, modelo.loja_id.in_(lojas), modelo.data >= inicio, modelo.data <= fim,
        condicao_registro_efetivo(modelo),
    )
    if produto_id is not None:
        q = q.filter(modelo.produto_id == produto_id)
    return _celulas(q.group_by(modelo.loja_id, modelo.produto_id, modelo.data))


def _lojas_com_venda(db, negocio_id, lojas, inicio, fim) -> set[tuple[int, date]]:
    q = db.query(VendaDiaria.loja_id, VendaDiaria.data).filter(
        VendaDiaria.negocio_id == negocio_id, VendaDiaria.loja_id.in_(lojas), VendaDiaria.data >= inicio,
        VendaDiaria.data <= fim, condicao_registro_efetivo(VendaDiaria),
    )
    return set(q.distinct().all())


def _recebido(db, negocio_id, lojas, inicio, fim, produto_id):
    q = (
        db.query(RomaneioEntrega.loja_id, RomaneioItem.produto_id, Romaneio.data_entrega,
                 func.sum(func.coalesce(RomaneioItem.quantidade_recebida, RomaneioItem.quantidade_final)))
        .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
        .join(Romaneio, Romaneio.id == RomaneioEntrega.romaneio_id)
        .filter(Romaneio.negocio_id == negocio_id, RomaneioEntrega.negocio_id == negocio_id,
                RomaneioEntrega.loja_id.in_(lojas), Romaneio.data_entrega >= inicio, Romaneio.data_entrega <= fim,
                RomaneioEntrega.expedido_em.isnot(None))
    )
    if produto_id is not None:
        q = q.filter(RomaneioItem.produto_id == produto_id)
    return _celulas(q.group_by(RomaneioEntrega.loja_id, RomaneioItem.produto_id, Romaneio.data_entrega))


def calcular(
    db: Session, negocio_id: int, lojas: list[int], inicio: date, fim: date, produto_id: int | None = None
) -> dict[Celula, Balanco]:
    """Balanço de cada loja × produto × dia do período (só as células em que dá para calcular)."""
    if not lojas:
        return {}
    horarios = dict(
        db.query(Loja.id, Loja.horario_fechamento).filter(Loja.negocio_id == negocio_id, Loja.id.in_(lojas)).all()
    )
    contagens = fechamentos(_lancamentos(db, negocio_id, lojas, inicio, fim, produto_id), horarios)
    return montar(
        inicio, fim, contagens,
        _recebido(db, negocio_id, lojas, inicio, fim, produto_id),
        _diarios(db, VendaDiaria, negocio_id, lojas, inicio, fim, produto_id),
        _diarios(db, PerdaDiaria, negocio_id, lojas, inicio, fim, produto_id),
        _lojas_com_venda(db, negocio_id, lojas, inicio, fim),
    )
