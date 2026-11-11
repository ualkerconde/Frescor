"""
Lançamento de perda (D110): a loja lança no app e o gestor vê e corrige no
SaaS. Regras de negócio aqui; os routers (`app/api/perdas_lancamento.py`)
só autenticam e traduzem erros.

Regras:
- Produto do mesmo negócio, ativo e habilitado (e não desativado) na loja.
- Quantidade > 0 na unidade do produto; UN tem de ser inteira (como D13a).
- Motivo de uma lista fixa (`MotivoPerda`); observação opcional (até 200).
- Data: a loja lança para hoje ou ontem (o descarte da noite pode ser
  lançado na manhã seguinte); nunca para o futuro. O gestor lança ou corrige
  qualquer dia passado das lojas da própria central.
- A loja corrige ou apaga o PRÓPRIO lançamento (de qualquer operador da loja)
  até o fim do dia seguinte ao da perda (D+1, na hora local); depois, só o
  gestor.
- Depois de cada mudança, `recalcular_perda_do_dia` grava a soma do dia em
  `perdas_diarias` (origem `manual`). Soma zero apaga a linha `manual` do
  dia. É o único lugar que escreve a perda manual a partir de agora (a
  importação de perdas por CSV sai da tela, D107).

`negocio_id`, `loja_id` e `central_producao_id` chegam sempre do usuário
autenticado (regra de ouro 1).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from app.models.lancamento_perda import LancamentoPerda, MotivoPerda
from app.models.loja import Loja
from app.models.perda_diaria import OrigemPerda, PerdaDiaria
from app.models.produto import Produto, UnidadeMedida
from app.models.produto_loja import ProdutoLoja
from app.models.usuario import Usuario
from app.services.necessidade_calculo import FUSO_PADRAO

DIAS_PARA_A_LOJA_CORRIGIR = 1  # D110: até o fim de D+1
DIAS_PARA_A_LOJA_LANCAR_ATRAS = 1  # hoje ou ontem
TAMANHO_OBSERVACAO = 200


class LancamentoInvalido(Exception):
    """Dado inválido (422)."""


class LancamentoNaoEncontrado(Exception):
    """Lançamento inexistente ou fora do escopo de quem pede (404)."""


class LancamentoBloqueado(Exception):
    """Fora do prazo da loja (409)."""


@dataclass(frozen=True)
class Lancamento:
    id: int
    data: date
    loja_id: int
    loja_codigo: str | None
    loja_nome: str
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    quantidade: Decimal
    motivo: str
    observacao: str | None
    lancado_por: str
    lancado_em: datetime
    alterado_por: str | None
    alterado_em: datetime | None
    loja_pode_alterar: bool


def hoje_local(agora_utc: datetime | None = None, fuso: str = FUSO_PADRAO) -> date:
    agora_utc = agora_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    return agora_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(fuso)).date()


def loja_pode_alterar(data_perda: date, hoje: date) -> bool:
    return hoje <= data_perda + timedelta(days=DIAS_PARA_A_LOJA_CORRIGIR)


# ------------------------------------------------------------------ validação

def _quantidade(valor, unidade: UnidadeMedida) -> Decimal:
    try:
        q = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise LancamentoInvalido("Informe a quantidade com número, como 3 ou 1,5.") from None
    if not q.is_finite() or q <= 0:
        raise LancamentoInvalido("A quantidade tem de ser maior que zero.")
    if q > Decimal("999999"):
        raise LancamentoInvalido("Quantidade grande demais. Confira o número.")
    if unidade == UnidadeMedida.UN and q != q.to_integral_value():
        raise LancamentoInvalido("Este produto é contado por unidade: a quantidade tem de ser inteira.")
    if q != q.quantize(Decimal("0.001")):
        raise LancamentoInvalido("Use no máximo 3 casas depois da vírgula.")
    return q


def _motivo(valor) -> MotivoPerda:
    try:
        return MotivoPerda(valor)
    except ValueError:
        raise LancamentoInvalido("Escolha o motivo: vencido, avariado ou outro.") from None


def _observacao(texto: str | None, motivo: MotivoPerda) -> str | None:
    texto = (texto or "").strip() or None
    if texto and len(texto) > TAMANHO_OBSERVACAO:
        raise LancamentoInvalido(f"A observação pode ter até {TAMANHO_OBSERVACAO} caracteres.")
    if motivo == MotivoPerda.OUTRO and not texto:
        raise LancamentoInvalido("Com o motivo \"outro\", escreva numa linha o que aconteceu.")
    return texto


def _produto_da_loja(db: Session, negocio_id: int, loja_id: int, produto_id: int) -> Produto:
    produto = db.query(Produto).filter(Produto.id == produto_id, Produto.negocio_id == negocio_id).first()
    if produto is None:
        raise LancamentoInvalido("Produto não encontrado.")
    if not produto.ativo:
        raise LancamentoInvalido("Este produto está desativado.")
    habilitado = db.query(ProdutoLoja).filter(
        ProdutoLoja.produto_id == produto.id, ProdutoLoja.loja_id == loja_id, ProdutoLoja.ativo.is_(True)
    ).first()
    if habilitado is None:
        raise LancamentoInvalido("Este produto não está ativo nesta loja.")
    return produto


# ------------------------------------------------------------------ gravação

def recalcular_perda_do_dia(db: Session, negocio_id: int, loja_id: int, produto_id: int, dia: date) -> None:
    """Grava em `perdas_diarias` (manual) a soma dos lançamentos do dia; soma zero apaga a linha."""
    soma = (
        db.query(func.coalesce(func.sum(LancamentoPerda.quantidade), 0))
        .filter(LancamentoPerda.negocio_id == negocio_id, LancamentoPerda.loja_id == loja_id,
                LancamentoPerda.produto_id == produto_id, LancamentoPerda.data == dia)
        .scalar()
    )
    filtro = (PerdaDiaria.negocio_id == negocio_id, PerdaDiaria.loja_id == loja_id,
              PerdaDiaria.produto_id == produto_id, PerdaDiaria.data == dia,
              PerdaDiaria.origem == OrigemPerda.MANUAL)
    if Decimal(soma) <= 0:
        db.query(PerdaDiaria).filter(*filtro).delete(synchronize_session=False)
        return
    stmt = pg_insert(PerdaDiaria).values(negocio_id=negocio_id, loja_id=loja_id, produto_id=produto_id, data=dia,
                                         quantidade=soma, origem=OrigemPerda.MANUAL)
    stmt = stmt.on_conflict_do_update(constraint="uq_perda_loja_produto_data_origem",
                                      set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()})
    db.execute(stmt)


def lancar(db: Session, negocio_id: int, loja_id: int, usuario_id: int, produto_id: int, quantidade, motivo,
           observacao: str | None = None, dia: date | None = None, *, pela_loja: bool,
           agora_utc: datetime | None = None) -> int:
    hoje = hoje_local(agora_utc)
    dia = dia or hoje
    if dia > hoje:
        raise LancamentoInvalido("Não dá para lançar perda de um dia que ainda não chegou.")
    if pela_loja and dia < hoje - timedelta(days=DIAS_PARA_A_LOJA_LANCAR_ATRAS):
        raise LancamentoInvalido("A loja lança a perda de hoje ou de ontem. Para dias anteriores, fale com o gestor.")
    produto = _produto_da_loja(db, negocio_id, loja_id, produto_id)
    m = _motivo(motivo)
    lanc = LancamentoPerda(
        negocio_id=negocio_id, loja_id=loja_id, produto_id=produto.id, data=dia,
        quantidade=_quantidade(quantidade, produto.unidade_medida), motivo=m,
        observacao=_observacao(observacao, m), lancado_por_usuario_id=usuario_id,
    )
    try:
        db.add(lanc)
        db.flush()
        recalcular_perda_do_dia(db, negocio_id, loja_id, produto.id, dia)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return lanc.id


def _buscar(db: Session, negocio_id: int, lancamento_id: int, lojas_permitidas: list[int]) -> LancamentoPerda:
    lanc = db.query(LancamentoPerda).filter(
        LancamentoPerda.id == lancamento_id, LancamentoPerda.negocio_id == negocio_id,
        LancamentoPerda.loja_id.in_(lojas_permitidas),
    ).first()
    if lanc is None:
        raise LancamentoNaoEncontrado("Lançamento não encontrado.")
    return lanc


def _checar_prazo_da_loja(lanc: LancamentoPerda, pela_loja: bool, agora_utc: datetime | None) -> None:
    if pela_loja and not loja_pode_alterar(lanc.data, hoje_local(agora_utc)):
        raise LancamentoBloqueado(
            "O prazo da loja para corrigir este lançamento terminou (fim do dia seguinte). Peça ao gestor."
        )


def alterar(db: Session, negocio_id: int, lojas_permitidas: list[int], usuario_id: int, lancamento_id: int,
            quantidade, motivo, observacao: str | None, *, pela_loja: bool,
            agora_utc: datetime | None = None) -> int:
    lanc = _buscar(db, negocio_id, lancamento_id, lojas_permitidas)
    _checar_prazo_da_loja(lanc, pela_loja, agora_utc)
    produto = db.get(Produto, lanc.produto_id)
    m = _motivo(motivo)
    lanc.quantidade = _quantidade(quantidade, produto.unidade_medida)
    lanc.motivo = m
    lanc.observacao = _observacao(observacao, m)
    lanc.alterado_por_usuario_id = usuario_id
    lanc.alterado_em = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        db.flush()
        recalcular_perda_do_dia(db, negocio_id, lanc.loja_id, lanc.produto_id, lanc.data)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return lanc.id


def apagar(db: Session, negocio_id: int, lojas_permitidas: list[int], lancamento_id: int, *, pela_loja: bool,
           agora_utc: datetime | None = None) -> None:
    lanc = _buscar(db, negocio_id, lancamento_id, lojas_permitidas)
    _checar_prazo_da_loja(lanc, pela_loja, agora_utc)
    chave = (lanc.loja_id, lanc.produto_id, lanc.data)
    try:
        db.delete(lanc)
        db.flush()
        recalcular_perda_do_dia(db, negocio_id, *chave)
        db.commit()
    except Exception:
        db.rollback()
        raise


# ------------------------------------------------------------------ leitura

def listar(db: Session, negocio_id: int, lojas: list[int], inicio: date, fim: date, produto_id: int | None = None,
           agora_utc: datetime | None = None) -> list[Lancamento]:
    if not lojas:
        return []
    hoje = hoje_local(agora_utc)
    alterou = aliased(Usuario)
    q = (
        db.query(LancamentoPerda, Loja, Produto, Usuario.nome, alterou.nome)
        .join(Loja, Loja.id == LancamentoPerda.loja_id)
        .join(Produto, Produto.id == LancamentoPerda.produto_id)
        .join(Usuario, Usuario.id == LancamentoPerda.lancado_por_usuario_id)
        .outerjoin(alterou, alterou.id == LancamentoPerda.alterado_por_usuario_id)
        .filter(LancamentoPerda.negocio_id == negocio_id, LancamentoPerda.loja_id.in_(lojas),
                LancamentoPerda.data >= inicio, LancamentoPerda.data <= fim)
    )
    if produto_id is not None:
        q = q.filter(LancamentoPerda.produto_id == produto_id)
    q = q.order_by(LancamentoPerda.data.desc(), LancamentoPerda.lancado_em.desc(), LancamentoPerda.id.desc())
    return [
        Lancamento(
            id=l.id, data=l.data, loja_id=lj.id, loja_codigo=lj.codigo, loja_nome=lj.nome, produto_id=p.id,
            produto_codigo=p.codigo, produto_nome=p.nome, unidade=p.unidade_medida.value, quantidade=l.quantidade,
            motivo=l.motivo.value, observacao=l.observacao, lancado_por=quem, lancado_em=l.lancado_em,
            alterado_por=quem_alterou, alterado_em=l.alterado_em, loja_pode_alterar=loja_pode_alterar(l.data, hoje),
        )
        for l, lj, p, quem, quem_alterou in q.all()
    ]
