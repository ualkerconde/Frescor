"""
Consultas da distribuição para o gestor (Fase 5 / E5, E6): o romaneio com
as entregas por loja e a situação de cada uma (D79, D85, D89), e as
divergências de recebimento (D78).

A situação de leitura ("a caminho", "sem confirmação", "confirmada com
atraso"...) é calculada na hora pelo `recebimento_service.situacao_entrega`
e não é gravada: muda sozinha quando o dia de entrega termina, sem job.

Isolamento (regra de ouro 1): negócio e central vêm do gestor autenticado;
romaneio de outra central ou negócio responde como inexistente.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.loja import Loja
from app.models.ordem_producao import OrdemProducao, TipoOrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.produto import Produto
from app.models.romaneio import Romaneio, StatusRomaneio
from app.models.romaneio_entrega import RomaneioEntrega
from app.models.romaneio_item import RomaneioItem
from app.services.distribuicao_service import NaoEncontrado
from app.services.recebimento_service import SituacaoLeitura, situacao_entrega


@dataclass(frozen=True)
class ItemRomaneio:
    item_id: int
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    quantidade_sugerida: Decimal
    quantidade_final: Decimal
    quantidade_recebida: Decimal | None
    motivo_divergencia: str | None
    observacao_divergencia: str | None
    motivo_edicao: str | None
    editado_em: datetime | None


@dataclass(frozen=True)
class EntregaRomaneio:
    entrega_id: int
    loja_id: int
    loja_codigo: str | None
    loja_nome: str
    situacao: SituacaoLeitura
    expedido_em: datetime | None
    recebido_em: datetime | None
    itens: list[ItemRomaneio]


@dataclass(frozen=True)
class ProducaoRomaneio:
    """Produção registrada e o total das finais de um produto (D69, D71)."""

    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    tipo_abastecimento: str
    planejado: Decimal
    produzido: Decimal | None
    total_final: Decimal


@dataclass(frozen=True)
class RomaneioDetalhe:
    romaneio_id: int
    ordem_id: int
    data_producao: date
    data_entrega: date
    status: str
    gerado_em: datetime
    aprovado_em: datetime | None
    # Rascunho com a produção registrada (ou corrigida) depois de gerado: "Gerar de novo" (D87).
    desatualizado: bool
    producao: list[ProducaoRomaneio]
    entregas: list[EntregaRomaneio]


def obter_romaneio(
    db: Session, negocio_id: int, central_producao_id: int, romaneio_id: int, agora: datetime | None = None
) -> RomaneioDetalhe:
    """Romaneio com a produção por produto e as entregas na ordem do código da loja."""
    agora = agora or datetime.utcnow()
    encontrado = (
        db.query(Romaneio, OrdemProducao.data_producao)
        .join(OrdemProducao, OrdemProducao.id == Romaneio.ordem_id)
        .filter(Romaneio.negocio_id == negocio_id, Romaneio.central_producao_id == central_producao_id,
                Romaneio.id == romaneio_id, OrdemProducao.negocio_id == negocio_id)
        .one_or_none()
    )
    if encontrado is None:
        raise NaoEncontrado("Romaneio não encontrado.")
    romaneio, data_producao = encontrado

    itens_por_entrega: dict[int, list[ItemRomaneio]] = {}
    totais: dict[int, Decimal] = {}
    for item, codigo, nome in (
        db.query(RomaneioItem, Produto.codigo, Produto.nome)
        .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
        .join(Produto, Produto.id == RomaneioItem.produto_id)
        .filter(RomaneioEntrega.romaneio_id == romaneio.id, RomaneioItem.negocio_id == negocio_id,
                Produto.negocio_id == negocio_id)
        .order_by(Produto.codigo, Produto.id)
    ):
        itens_por_entrega.setdefault(item.entrega_id, []).append(ItemRomaneio(
            item_id=item.id, produto_id=item.produto_id, produto_codigo=codigo, produto_nome=nome,
            unidade=item.unidade.value, quantidade_sugerida=Decimal(item.quantidade_sugerida),
            quantidade_final=Decimal(item.quantidade_final),
            quantidade_recebida=Decimal(item.quantidade_recebida) if item.quantidade_recebida is not None else None,
            motivo_divergencia=item.motivo_divergencia.value if item.motivo_divergencia else None,
            observacao_divergencia=item.observacao_divergencia, motivo_edicao=item.motivo_edicao,
            editado_em=item.editado_em,
        ))
        totais[item.produto_id] = totais.get(item.produto_id, Decimal(0)) + Decimal(item.quantidade_final)

    entregas = []
    for entrega, loja_codigo, loja_nome in (
        db.query(RomaneioEntrega, Loja.codigo, Loja.nome)
        .join(Loja, Loja.id == RomaneioEntrega.loja_id)
        .filter(RomaneioEntrega.romaneio_id == romaneio.id, RomaneioEntrega.negocio_id == negocio_id,
                Loja.negocio_id == negocio_id)
        .order_by(Loja.codigo, Loja.id)
    ):
        itens = itens_por_entrega.get(entrega.id, [])
        diferenca = any(i.quantidade_recebida is not None and i.quantidade_recebida != i.quantidade_final
                        for i in itens)
        entregas.append(EntregaRomaneio(
            entrega_id=entrega.id, loja_id=entrega.loja_id, loja_codigo=loja_codigo, loja_nome=loja_nome,
            situacao=situacao_entrega(entrega.situacao, romaneio.data_entrega, entrega.recebido_em, agora,
                                      diferenca),
            expedido_em=entrega.expedido_em, recebido_em=entrega.recebido_em, itens=itens,
        ))

    producao = []
    desatualizado = False
    for item, codigo, nome in (
        db.query(OrdemProducaoItem, Produto.codigo, Produto.nome)
        .join(Produto, Produto.id == OrdemProducaoItem.produto_id)
        .filter(OrdemProducaoItem.ordem_id == romaneio.ordem_id, OrdemProducaoItem.negocio_id == negocio_id,
                Produto.negocio_id == negocio_id)
        .order_by(Produto.codigo, Produto.id)
    ):
        if (romaneio.status == StatusRomaneio.RASCUNHO and item.producao_registrada_em is not None
                and item.producao_registrada_em > romaneio.gerado_em):
            desatualizado = True
        if item.produto_id not in totais:
            continue
        producao.append(ProducaoRomaneio(
            produto_id=item.produto_id, produto_codigo=codigo, produto_nome=nome, unidade=item.unidade.value,
            tipo_abastecimento=item.tipo_abastecimento.value, planejado=_planejado(db, negocio_id, item.id),
            produzido=Decimal(item.quantidade_produzida) if item.quantidade_produzida is not None else None,
            total_final=totais[item.produto_id],
        ))
    return RomaneioDetalhe(
        romaneio_id=romaneio.id, ordem_id=romaneio.ordem_id, data_producao=data_producao,
        data_entrega=romaneio.data_entrega, status=romaneio.status.value, gerado_em=romaneio.gerado_em,
        aprovado_em=romaneio.aprovado_em if romaneio.status == StatusRomaneio.APROVADO else None,
        desatualizado=desatualizado, producao=producao, entregas=entregas,
    )


@dataclass(frozen=True)
class ItemProducaoOrdem:
    """Um produto da ordem aprovada, para registrar a produção real (D69)."""

    item_id: int
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    tipo_abastecimento: str
    planejado: Decimal
    produzido: Decimal | None
    registrado_em: datetime | None


@dataclass(frozen=True)
class ResumoRomaneio:
    romaneio_id: int
    status: str
    entregas: int
    # Contagem por situação de leitura (aguardando_saida, a_caminho, ...).
    situacoes: dict[str, int]


@dataclass(frozen=True)
class OrdemDistribuicao:
    ordem_id: int
    data_producao: date
    data_entrega: date
    status_ordem: str
    itens: list[ItemProducaoOrdem]
    romaneio: ResumoRomaneio | None


def distribuicao_do_dia(
    db: Session, negocio_id: int, central_producao_id: int, data_entrega: date, agora: datetime | None = None
) -> list[OrdemDistribuicao]:
    """Ordens programadas da central com entrega no dia, com a produção registrada e o romaneio (se houver)."""
    agora = agora or datetime.utcnow()
    ordens = (
        db.query(OrdemProducao)
        .filter(OrdemProducao.negocio_id == negocio_id, OrdemProducao.central_producao_id == central_producao_id,
                OrdemProducao.data_entrega == data_entrega, OrdemProducao.tipo == TipoOrdemProducao.PROGRAMADA)
        .order_by(OrdemProducao.data_producao, OrdemProducao.id)
        .all()
    )
    resultado = []
    for ordem in ordens:
        itens = [
            ItemProducaoOrdem(
                item_id=item.id, produto_id=item.produto_id, produto_codigo=codigo, produto_nome=nome,
                unidade=item.unidade.value, tipo_abastecimento=item.tipo_abastecimento.value,
                planejado=_planejado(db, negocio_id, item.id),
                produzido=Decimal(item.quantidade_produzida) if item.quantidade_produzida is not None else None,
                registrado_em=item.producao_registrada_em,
            )
            for item, codigo, nome in (
                db.query(OrdemProducaoItem, Produto.codigo, Produto.nome)
                .join(Produto, Produto.id == OrdemProducaoItem.produto_id)
                .filter(OrdemProducaoItem.ordem_id == ordem.id, OrdemProducaoItem.negocio_id == negocio_id,
                        Produto.negocio_id == negocio_id)
                .order_by(OrdemProducaoItem.tipo_abastecimento, Produto.codigo, Produto.id)
            )
        ]
        romaneio = (
            db.query(Romaneio)
            .filter(Romaneio.negocio_id == negocio_id, Romaneio.ordem_id == ordem.id)
            .one_or_none()
        )
        resumo = None
        if romaneio is not None:
            situacoes: dict[str, int] = {}
            entregas = db.query(RomaneioEntrega).filter(
                RomaneioEntrega.negocio_id == negocio_id, RomaneioEntrega.romaneio_id == romaneio.id).all()
            for entrega in entregas:
                s = situacao_entrega(entrega.situacao, romaneio.data_entrega, entrega.recebido_em, agora).situacao
                situacoes[s] = situacoes.get(s, 0) + 1
            resumo = ResumoRomaneio(romaneio.id, romaneio.status.value, len(entregas), situacoes)
        resultado.append(OrdemDistribuicao(
            ordem_id=ordem.id, data_producao=ordem.data_producao, data_entrega=ordem.data_entrega,
            status_ordem=ordem.status.value, itens=itens, romaneio=resumo,
        ))
    return resultado


@dataclass(frozen=True)
class Divergencia:
    data_entrega: date
    loja_id: int
    loja_codigo: str | None
    loja_nome: str
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    quantidade_enviada: Decimal
    quantidade_recebida: Decimal
    diferenca: Decimal  # recebida − enviada (negativa = chegou menos)
    motivo: str
    observacao: str | None
    recebido_em: datetime


@dataclass(frozen=True)
class TotalDivergencia:
    unidade: str
    enviada: Decimal
    recebida: Decimal
    diferenca: Decimal


def listar_divergencias(
    db: Session, negocio_id: int, central_producao_id: int, data_inicio: date, data_fim: date
) -> tuple[list[Divergencia], list[TotalDivergencia]]:
    """D78: itens recebidos diferentes do enviado, por dia de entrega, loja e produto, e os totais por unidade."""
    linhas = []
    totais: dict[str, list[Decimal]] = {}
    for item, entrega, data_entrega, loja_codigo, loja_nome, produto_codigo, produto_nome in (
        db.query(RomaneioItem, RomaneioEntrega, Romaneio.data_entrega, Loja.codigo, Loja.nome, Produto.codigo,
                 Produto.nome)
        .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
        .join(Romaneio, Romaneio.id == RomaneioEntrega.romaneio_id)
        .join(Loja, Loja.id == RomaneioEntrega.loja_id)
        .join(Produto, Produto.id == RomaneioItem.produto_id)
        .filter(
            Romaneio.negocio_id == negocio_id, Romaneio.central_producao_id == central_producao_id,
            RomaneioItem.negocio_id == negocio_id, Loja.negocio_id == negocio_id, Produto.negocio_id == negocio_id,
            Romaneio.data_entrega >= data_inicio, Romaneio.data_entrega <= data_fim,
            RomaneioItem.quantidade_recebida.isnot(None),
            RomaneioItem.quantidade_recebida != RomaneioItem.quantidade_final,
        )
        .order_by(Romaneio.data_entrega, Loja.codigo, Loja.id, Produto.codigo, Produto.id)
    ):
        enviada, recebida = Decimal(item.quantidade_final), Decimal(item.quantidade_recebida)
        linhas.append(Divergencia(
            data_entrega=data_entrega, loja_id=entrega.loja_id, loja_codigo=loja_codigo, loja_nome=loja_nome,
            produto_id=item.produto_id, produto_codigo=produto_codigo, produto_nome=produto_nome,
            unidade=item.unidade.value, quantidade_enviada=enviada, quantidade_recebida=recebida,
            diferenca=recebida - enviada, motivo=item.motivo_divergencia.value,
            observacao=item.observacao_divergencia, recebido_em=entrega.recebido_em,
        ))
        t = totais.setdefault(item.unidade.value, [Decimal(0), Decimal(0)])
        t[0] += enviada
        t[1] += recebida
    return linhas, [TotalDivergencia(u, e, r, r - e) for u, (e, r) in sorted(totais.items())]


def _planejado(db: Session, negocio_id: int, item_id: int) -> Decimal:
    """D54: o planejado é a soma das finais das linhas da ordem."""
    total = Decimal(0)
    for (final,) in db.query(OrdemProducaoLinha.quantidade_final).filter(
        OrdemProducaoLinha.negocio_id == negocio_id, OrdemProducaoLinha.item_id == item_id
    ):
        total += Decimal(final) if final is not None else Decimal(0)
    return total
