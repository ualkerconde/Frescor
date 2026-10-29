"""
Eventos (datas atípicas, doc §4.3) do lado do serviço (Fase 3 / F3):

1. Carga para o motor de previsão: `eventos_das_lojas` devolve, por loja,
   os eventos que valem para ela num período, já no formato puro do
   núcleo de cálculo (`EventoAplicavel`).
2. Cadastro mínimo pelo gestor (D24): criar, listar e apagar.

Escopo (D8 e D27, docs/STATUS.md):
- Todo evento criado pelo gestor é da central dele. "Todas as lojas" =
  todas as lojas da central do evento (inclusive as que forem criadas
  depois); "lojas específicas" = lojas da central do gestor.
- Evento antigo sem central (migration 0018): "todas as lojas" vale para
  o negócio inteiro.
- "Lojas do evento" (escopo efetivo): as da central, as do negócio (evento
  antigo de "todas") ou as listadas em `eventos_lojas`.
- Listagem: eventos da central do gestor, eventos antigos de "todas" e
  eventos que listam alguma loja dele. Lojas de outras centrais não
  aparecem na resposta.
- Apagar: só se todas as lojas do evento forem da central do gestor;
  senão 403. Evento que o gestor não vê (outra central, outro negócio,
  inexistente) -> "não encontrado", sem distinguir os casos.
- Data passada é aceita: cadastrar um evento que já aconteceu tira esses
  dias da base da previsão.

Este serviço não conhece HTTP: erros de validação viram `EventoInvalido`
(422 na rota); fora do escopo vira `EventoNaoEncontrado` (404) ou
`EventoForaDoEscopo` (403).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste
from app.models.loja import Loja
from app.models.produto import Produto
from app.services.escopo_service import ids_lojas_do_gestor
from app.services.previsao_calculo import EventoAplicavel

PERIODO_MAXIMO_DIAS = 366
VALOR_MAXIMO = Decimal("999999.9999")  # Numeric(10, 4)
TAMANHO_MAXIMO_NOME = 255


class EventoInvalido(ValueError):
    pass


class EventoNaoEncontrado(LookupError):
    pass


class EventoForaDoEscopo(PermissionError):
    pass


# ---------------------------------------------------------------- motor


def eventos_das_lojas(
    db: Session, negocio_id: int, loja_ids: list[int], inicio: date, fim: date
) -> dict[int, list[EventoAplicavel]]:
    """Eventos do negócio que tocam [inicio, fim], por loja (só as lojas pedidas)."""
    resultado: dict[int, list[EventoAplicavel]] = {loja_id: [] for loja_id in loja_ids}
    if not loja_ids:
        return resultado
    eventos = (
        db.query(Evento)
        .filter(Evento.negocio_id == negocio_id, Evento.data_inicio <= fim, Evento.data_fim >= inicio)
        .order_by(Evento.id)
        .all()
    )
    if not eventos:
        return resultado
    central_da_loja = dict(
        db.query(Loja.id, Loja.central_producao_id).filter(Loja.negocio_id == negocio_id, Loja.id.in_(loja_ids))
    )
    ids = [e.id for e in eventos]
    lojas_por_evento: dict[int, set[int]] = defaultdict(set)
    for evento_id, loja_id in db.query(EventoLoja.evento_id, EventoLoja.loja_id).filter(
        EventoLoja.negocio_id == negocio_id, EventoLoja.evento_id.in_(ids), EventoLoja.loja_id.in_(loja_ids)
    ):
        lojas_por_evento[evento_id].add(loja_id)
    produtos_por_evento: dict[int, set[int]] = defaultdict(set)
    for evento_id, produto_id in db.query(EventoProduto.evento_id, EventoProduto.produto_id).filter(
        EventoProduto.negocio_id == negocio_id, EventoProduto.evento_id.in_(ids)
    ):
        produtos_por_evento[evento_id].add(produto_id)

    for e in eventos:
        aplicavel = EventoAplicavel(
            id=e.id,
            nome=e.nome,
            data_inicio=e.data_inicio,
            data_fim=e.data_fim,
            tipo_ajuste=e.tipo_ajuste,
            valor_ajuste=Decimal(e.valor_ajuste),
            produto_ids=None
            if e.escopo_produto == EscopoProduto.TODOS
            else frozenset(produtos_por_evento[e.id]),
        )
        if e.escopo_loja == EscopoLoja.TODAS:
            lojas = [
                lid for lid in loja_ids
                if lid in central_da_loja
                and (e.central_producao_id is None or central_da_loja[lid] == e.central_producao_id)
            ]
        else:
            lojas = lojas_por_evento[e.id]
        for loja_id in lojas:
            resultado[loja_id].append(aplicavel)
    return resultado


# ---------------------------------------------------------------- cadastro


@dataclass(frozen=True)
class EventoDetalhe:
    id: int
    nome: str
    data_inicio: date
    data_fim: date
    tipo_ajuste: TipoAjuste
    valor_ajuste: Decimal
    escopo_loja: EscopoLoja
    # Só as lojas da central do gestor (vazio quando escopo_loja = todas).
    loja_ids: list[int]
    escopo_produto: EscopoProduto
    produto_ids: list[int]
    # Todas as lojas do evento são da central do gestor (senão apagar -> 403). Fase 6 / C5.
    pode_apagar: bool = True


def _validar(nome, data_inicio, data_fim, valor_ajuste, escopo_loja, loja_ids, produto_ids) -> str:
    nome = (nome or "").strip()
    if not nome:
        raise EventoInvalido("Informe o nome do evento.")
    if len(nome) > TAMANHO_MAXIMO_NOME:
        raise EventoInvalido(f"O nome do evento pode ter no máximo {TAMANHO_MAXIMO_NOME} caracteres.")
    if data_fim < data_inicio:
        raise EventoInvalido("A data final do evento não pode ser antes da inicial.")
    if (data_fim - data_inicio).days + 1 > PERIODO_MAXIMO_DIAS:
        raise EventoInvalido(f"O evento pode durar no máximo {PERIODO_MAXIMO_DIAS} dias.")
    if not valor_ajuste.is_finite():
        raise EventoInvalido("Informe um número no valor do ajuste.")
    if valor_ajuste < 0:
        raise EventoInvalido("O valor do ajuste não pode ser negativo.")
    if valor_ajuste > VALOR_MAXIMO:
        raise EventoInvalido("O valor do ajuste é grande demais.")
    if valor_ajuste.normalize().as_tuple().exponent < -4:
        raise EventoInvalido("O valor do ajuste pode ter no máximo 4 casas decimais.")
    if escopo_loja == EscopoLoja.TODAS:
        if loja_ids:
            raise EventoInvalido("Com \"todas as lojas\", não informe lojas.")
    else:
        if not loja_ids:
            raise EventoInvalido("Escolha pelo menos uma loja.")
        if len(set(loja_ids)) != len(loja_ids):
            raise EventoInvalido("A mesma loja foi informada mais de uma vez.")
    if produto_ids is not None and len(set(produto_ids)) != len(produto_ids):
        raise EventoInvalido("O mesmo produto foi informado mais de uma vez.")
    return nome


def criar_evento(
    db: Session,
    gestor: GestorCentralAutenticado,
    nome: str,
    data_inicio: date,
    data_fim: date,
    tipo_ajuste: TipoAjuste,
    valor_ajuste: Decimal,
    escopo_loja: EscopoLoja,
    loja_ids: list[int] | None,
    produto_ids: list[int] | None,
) -> EventoDetalhe:
    """
    Cria evento da central do gestor: para todas as lojas da central ou
    para lojas específicas dela. `produto_ids` vazio ou None = todos os
    produtos.
    """
    loja_ids = loja_ids or []
    produto_ids = produto_ids or None
    nome = _validar(nome, data_inicio, data_fim, valor_ajuste, escopo_loja, loja_ids, produto_ids)

    escopo = set(ids_lojas_do_gestor(db, gestor))
    for loja_id in loja_ids:
        if loja_id not in escopo:
            raise EventoInvalido(f"Loja {loja_id} não encontrada.")
    if produto_ids is not None:
        do_negocio = {
            pid
            for (pid,) in db.query(Produto.id).filter(
                Produto.negocio_id == gestor.negocio_id, Produto.id.in_(produto_ids)
            )
        }
        for produto_id in produto_ids:
            if produto_id not in do_negocio:
                raise EventoInvalido(f"Produto {produto_id} não encontrado.")

    evento = Evento(
        negocio_id=gestor.negocio_id,
        central_producao_id=gestor.central_producao_id,
        nome=nome,
        data_inicio=data_inicio,
        data_fim=data_fim,
        escopo_loja=escopo_loja,
        escopo_produto=EscopoProduto.TODOS if produto_ids is None else EscopoProduto.ESPECIFICOS,
        tipo_ajuste=tipo_ajuste,
        valor_ajuste=valor_ajuste,
    )
    db.add(evento)
    db.flush()
    db.add_all(EventoLoja(evento_id=evento.id, loja_id=lid, negocio_id=gestor.negocio_id) for lid in loja_ids)
    if produto_ids is not None:
        db.add_all(
            EventoProduto(evento_id=evento.id, produto_id=pid, negocio_id=gestor.negocio_id) for pid in produto_ids
        )
    db.commit()
    return _detalhe(db, evento, escopo)


def _consulta_visiveis(db: Session, gestor: GestorCentralAutenticado, escopo: set[int]):
    lista_loja_da_central = exists().where(EventoLoja.evento_id == Evento.id, EventoLoja.loja_id.in_(escopo))
    return db.query(Evento).filter(
        Evento.negocio_id == gestor.negocio_id,
        or_(
            Evento.central_producao_id == gestor.central_producao_id,
            and_(Evento.central_producao_id.is_(None), Evento.escopo_loja == EscopoLoja.TODAS),
            lista_loja_da_central,
        ),
    )


def _lojas_do_evento(db: Session, evento: Evento) -> set[int]:
    """Escopo efetivo de lojas do evento (ver docstring do módulo)."""
    if evento.escopo_loja == EscopoLoja.TODAS:
        consulta = db.query(Loja.id).filter(Loja.negocio_id == evento.negocio_id)
        if evento.central_producao_id is not None:
            consulta = consulta.filter(Loja.central_producao_id == evento.central_producao_id)
        return {lid for (lid,) in consulta}
    return {lid for (lid,) in db.query(EventoLoja.loja_id).filter(EventoLoja.evento_id == evento.id)}


def _detalhe(db: Session, evento: Evento, escopo: set[int]) -> EventoDetalhe:
    lojas = (
        []
        if evento.escopo_loja == EscopoLoja.TODAS
        else sorted(
            lid for (lid,) in db.query(EventoLoja.loja_id).filter(EventoLoja.evento_id == evento.id) if lid in escopo
        )
    )
    produtos = sorted(pid for (pid,) in db.query(EventoProduto.produto_id).filter(EventoProduto.evento_id == evento.id))
    return EventoDetalhe(
        id=evento.id,
        nome=evento.nome,
        data_inicio=evento.data_inicio,
        data_fim=evento.data_fim,
        tipo_ajuste=evento.tipo_ajuste,
        valor_ajuste=Decimal(evento.valor_ajuste),
        escopo_loja=evento.escopo_loja,
        loja_ids=lojas,
        escopo_produto=evento.escopo_produto,
        produto_ids=produtos,
        pode_apagar=_lojas_do_evento(db, evento) <= escopo,
    )


def listar_eventos(
    db: Session, gestor: GestorCentralAutenticado, data_inicio: date | None, data_fim: date | None
) -> list[EventoDetalhe]:
    """Eventos visíveis ao gestor; com datas, só os que tocam o período."""
    escopo = set(ids_lojas_do_gestor(db, gestor))
    consulta = _consulta_visiveis(db, gestor, escopo)
    if data_inicio is not None:
        consulta = consulta.filter(Evento.data_fim >= data_inicio)
    if data_fim is not None:
        consulta = consulta.filter(Evento.data_inicio <= data_fim)
    return [_detalhe(db, e, escopo) for e in consulta.order_by(Evento.data_inicio, Evento.id)]


def apagar_evento(db: Session, gestor: GestorCentralAutenticado, evento_id: int) -> None:
    escopo = set(ids_lojas_do_gestor(db, gestor))
    evento = _consulta_visiveis(db, gestor, escopo).filter(Evento.id == evento_id).first()
    if evento is None:
        raise EventoNaoEncontrado("Evento não encontrado.")
    if not _lojas_do_evento(db, evento) <= escopo:
        raise EventoForaDoEscopo("Este evento vale também para lojas de outra central e não pode ser apagado aqui.")
    db.query(EventoLoja).filter(EventoLoja.evento_id == evento.id).delete(synchronize_session=False)
    db.query(EventoProduto).filter(EventoProduto.evento_id == evento.id).delete(synchronize_session=False)
    db.delete(evento)
    db.commit()
