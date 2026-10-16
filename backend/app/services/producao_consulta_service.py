"""
Leitura das ordens de produção para a API e a tela (Fase 4 / N7).

- `listar_ordens`: ordens da central numa data de produção, em resumo
  (situação, totais por unidade, quantas linhas o gestor editou e quantas
  ainda estão sem quantidade). "Linhas editadas" é o que a tela mostra ao
  pedir confirmação antes de regerar um rascunho (D58).
- `obter_ordem`: a ordem com os itens (por produto: totais sugerido e
  final, D54) e as linhas por loja (quantidades, avisos, componentes da
  conta, edição).

Ordem de outra central ou de outro negócio não existe para o gestor
(`OrdemNaoEncontrada`). `negocio_id` e `central_producao_id` vêm do gestor
autenticado.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.loja import Loja
from app.models.ordem_producao import OrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.services.producao_service import OrdemNaoEncontrada


@dataclass
class TotalUnidade:
    unidade: str
    sugerido: Decimal = Decimal(0)
    final: Decimal = Decimal(0)


@dataclass
class LinhaOrdem:
    id: int
    loja_id: int
    loja_codigo: str | None
    loja_nome: str
    quantidade_sugerida: Decimal | None
    quantidade_final: Decimal | None
    editada: bool
    editado_em: datetime | None
    motivo_edicao: str | None
    avisos: list
    componentes: dict


@dataclass
class ItemOrdem:
    id: int
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    tipo_abastecimento: str
    unidade: str
    total_sugerido: Decimal
    total_final: Decimal
    linhas: list[LinhaOrdem]


@dataclass
class ResumoOrdem:
    id: int
    data_producao: date
    data_entrega: date
    tipo: str
    status: str
    versao_metodo: str
    referencia_previsao: date | None
    gerado_em: datetime
    gerado_por: str | None
    aprovado_em: datetime | None
    aprovado_por: str | None
    linhas: int
    linhas_editadas: int
    linhas_sem_quantidade: int
    totais: list[TotalUnidade]
    itens: list[ItemOrdem] = field(default_factory=list)


def _nomes_usuarios(db: Session, negocio_id: int, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(db.query(Usuario.id, Usuario.nome).filter(Usuario.negocio_id == negocio_id, Usuario.id.in_(ids)))


def _montar(db: Session, negocio_id: int, ordens: list[OrdemProducao], com_itens: bool) -> list[ResumoOrdem]:
    if not ordens:
        return []
    ids = [o.id for o in ordens]
    linhas_por_ordem: dict[int, list] = defaultdict(list)
    for linha, item, produto, loja in (
        db.query(OrdemProducaoLinha, OrdemProducaoItem, Produto, Loja)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(Produto, Produto.id == OrdemProducaoItem.produto_id)
        .join(Loja, Loja.id == OrdemProducaoLinha.loja_id)
        .filter(
            OrdemProducaoItem.ordem_id.in_(ids),
            OrdemProducaoItem.negocio_id == negocio_id,
            OrdemProducaoLinha.negocio_id == negocio_id,
        )
    ):
        linhas_por_ordem[item.ordem_id].append((linha, item, produto, loja))
    nomes = _nomes_usuarios(
        db, negocio_id, {o.gerado_por_usuario_id for o in ordens} | {o.aprovado_por_usuario_id for o in ordens}
    )

    resumos = []
    for o in ordens:
        totais: dict[str, TotalUnidade] = {}
        itens: dict[int, ItemOrdem] = {}
        editadas = sem_quantidade = 0
        registros = sorted(
            linhas_por_ordem[o.id],
            key=lambda r: (r[2].codigo or "", r[2].id, r[3].codigo or "", r[3].id),
        )
        for linha, item, produto, loja in registros:
            unidade = item.unidade.value
            total = totais.setdefault(unidade, TotalUnidade(unidade))
            sugerida = Decimal(linha.quantidade_sugerida) if linha.quantidade_sugerida is not None else None
            final = Decimal(linha.quantidade_final) if linha.quantidade_final is not None else None
            total.sugerido += sugerida or 0
            total.final += final or 0
            editadas += linha.editado_em is not None
            sem_quantidade += final is None
            if com_itens:
                atual = itens.get(item.id)
                if atual is None:
                    atual = itens[item.id] = ItemOrdem(
                        id=item.id, produto_id=produto.id, produto_codigo=produto.codigo, produto_nome=produto.nome,
                        tipo_abastecimento=item.tipo_abastecimento.value, unidade=unidade,
                        total_sugerido=Decimal(0), total_final=Decimal(0), linhas=[],
                    )
                atual.total_sugerido += sugerida or 0
                atual.total_final += final or 0
                atual.linhas.append(LinhaOrdem(
                    id=linha.id, loja_id=loja.id, loja_codigo=loja.codigo, loja_nome=loja.nome,
                    quantidade_sugerida=sugerida, quantidade_final=final, editada=linha.editado_em is not None,
                    editado_em=linha.editado_em, motivo_edicao=linha.motivo_edicao, avisos=list(linha.avisos),
                    componentes=dict(linha.componentes),
                ))
        resumos.append(ResumoOrdem(
            id=o.id, data_producao=o.data_producao, data_entrega=o.data_entrega, tipo=o.tipo.value,
            status=o.status.value, versao_metodo=o.versao_metodo, referencia_previsao=o.referencia_previsao,
            gerado_em=o.gerado_em, gerado_por=nomes.get(o.gerado_por_usuario_id), aprovado_em=o.aprovado_em,
            aprovado_por=nomes.get(o.aprovado_por_usuario_id), linhas=len(registros), linhas_editadas=editadas,
            linhas_sem_quantidade=sem_quantidade, totais=sorted(totais.values(), key=lambda t: t.unidade),
            itens=list(itens.values()),
        ))
    return resumos


def listar_ordens(db: Session, negocio_id: int, central_producao_id: int, data_producao: date) -> list[ResumoOrdem]:
    ordens = (
        db.query(OrdemProducao)
        .filter(
            OrdemProducao.negocio_id == negocio_id,
            OrdemProducao.central_producao_id == central_producao_id,
            OrdemProducao.data_producao == data_producao,
        )
        .order_by(OrdemProducao.tipo, OrdemProducao.id)
        .all()
    )
    return _montar(db, negocio_id, ordens, com_itens=False)


def obter_ordem(db: Session, negocio_id: int, central_producao_id: int, ordem_id: int) -> ResumoOrdem:
    ordem = (
        db.query(OrdemProducao)
        .filter(
            OrdemProducao.negocio_id == negocio_id,
            OrdemProducao.central_producao_id == central_producao_id,
            OrdemProducao.id == ordem_id,
        )
        .one_or_none()
    )
    if ordem is None:
        raise OrdemNaoEncontrada("Ordem de produção não encontrada.")
    return _montar(db, negocio_id, [ordem], com_itens=True)[0]
