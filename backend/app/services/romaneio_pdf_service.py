"""
Impressão do romaneio aprovado em PDF (Fase 5 / E8, D81): a folha de carga
primeiro e depois uma folha por loja.

Por que assim: a folha de carga é o que a expedição confere ao montar o
caminhão (total por produto, lojas da viagem); a folha da loja vai junto
com a mercadoria e é assinada na entrega. Uma loja nunca divide a folha com
outra, para que cada folha possa ser destacada e entregue sozinha.

Regras:
- Só romaneio APROVADO imprime (o rascunho ainda muda) ->
  `OperacaoNaoPermitida` (a rota responde 409).
- Folha de carga: total de cada produto = soma das lojas impressas; abaixo,
  a lista das lojas. Com o filtro de lojas (`lojas`), soma só as escolhidas
  (D81). Produto com total 0 não sai na carga.
- Uma folha por loja, na ordem do código; se não couber numa página,
  continua na seguinte com o mesmo cabeçalho. A folha lista todos os
  produtos da entrega, inclusive os que ficaram com 0 no rateio (D86),
  para a loja saber o que não vai (D94).
- Cada folha: central, loja (ou "Folha de carga"), data de entrega e de
  produção, hora da impressão (São Paulo), produtos com unidade e
  quantidade, e as linhas "Conferido por" e "Recebido por".
- O gestor escolhe as lojas (`lojas`): None = todas; uma lista = essas.
  Loja que não está neste romaneio -> `DistribuicaoInvalida` (422).

`negocio_id` e `central_producao_id` vêm do gestor autenticado; romaneio
de outra central ou negócio -> `NaoEncontrado` (404).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.models.central_producao import CentralProducao
from app.models.loja import Loja
from app.models.ordem_producao import OrdemProducao
from app.models.produto import Produto, UnidadeMedida
from app.models.romaneio import StatusRomaneio
from app.models.romaneio_entrega import RomaneioEntrega
from app.models.romaneio_item import RomaneioItem
from app.services.distribuicao_service import (
    DistribuicaoInvalida,
    OperacaoNaoPermitida,
    _buscar_romaneio,
)
from app.services.ordem_pdf_service import (
    _APOIO,
    _LINHA,
    _TEXTO,
    _TITULO,
    _ZEBRA,
    FUSO,
    _data,
    formatar_quantidade,
)

TITULO_CARGA = "Folha de carga"


@dataclass
class LinhaFolha:
    produto: str
    unidade: str
    quantidade: Decimal


@dataclass
class FolhaLoja:
    loja: str
    itens: list[LinhaFolha] = field(default_factory=list)


@dataclass
class RomaneioImpressao:
    central: str
    data_producao: date
    data_entrega: date
    carga: list[LinhaFolha]
    lojas: list[FolhaLoja]


def _rotulo(codigo: str | None, nome: str) -> str:
    return f"{codigo} · {nome}" if codigo else nome


def montar_impressao(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    romaneio_id: int,
    lojas: Sequence[int] | None = None,
) -> RomaneioImpressao:
    romaneio = _buscar_romaneio(db, negocio_id, central_producao_id, romaneio_id)
    if romaneio.status != StatusRomaneio.APROVADO:
        raise OperacaoNaoPermitida("Só o romaneio aprovado pode ser impresso. Aprove o romaneio antes de imprimir.")

    entregas = (
        db.query(RomaneioEntrega, Loja)
        .join(Loja, Loja.id == RomaneioEntrega.loja_id)
        .filter(RomaneioEntrega.negocio_id == negocio_id, RomaneioEntrega.romaneio_id == romaneio.id)
        .order_by(Loja.codigo, Loja.nome, Loja.id)
        .all()
    )
    if lojas is not None:
        do_romaneio = {loja.id for _, loja in entregas}
        if not lojas or any(l not in do_romaneio for l in lojas):
            raise DistribuicaoInvalida("Loja não encontrada neste romaneio. Escolha as lojas da lista.")
        escolhidas = set(lojas)
        entregas = [(e, loja) for e, loja in entregas if loja.id in escolhidas]

    itens = (
        db.query(RomaneioItem, Produto)
        .join(Produto, Produto.id == RomaneioItem.produto_id)
        .filter(RomaneioItem.negocio_id == negocio_id, RomaneioItem.entrega_id.in_([e.id for e, _ in entregas]))
        .order_by(Produto.codigo, Produto.nome, Produto.id)
        .all()
    )
    por_entrega: dict[int, list[LinhaFolha]] = {}
    carga: dict[int, LinhaFolha] = {}
    for item, produto in itens:
        unidade = "kg" if item.unidade == UnidadeMedida.KG else "un"
        nome = _rotulo(produto.codigo, produto.nome)
        quantidade = Decimal(item.quantidade_final)
        por_entrega.setdefault(item.entrega_id, []).append(LinhaFolha(nome, unidade, quantidade))
        total = carga.setdefault(produto.id, LinhaFolha(nome, unidade, Decimal(0)))
        total.quantidade += quantidade

    central = db.query(CentralProducao.nome).filter(
        CentralProducao.negocio_id == negocio_id, CentralProducao.id == central_producao_id
    ).scalar()
    data_producao = db.query(OrdemProducao.data_producao).filter(
        OrdemProducao.negocio_id == negocio_id, OrdemProducao.id == romaneio.ordem_id
    ).scalar()
    return RomaneioImpressao(
        central=central,
        data_producao=data_producao,
        data_entrega=romaneio.data_entrega,
        carga=[linha for linha in carga.values() if linha.quantidade > 0],
        lojas=[FolhaLoja(_rotulo(loja.codigo, loja.nome), por_entrega.get(e.id, [])) for e, loja in entregas],
    )


# ---- PDF ----

class _InicioFolha(Flowable):
    """Marca, sem ocupar espaço, o título da página (o cabeçalho é desenhado no fim da página)."""

    def __init__(self, titulo: str):
        super().__init__()
        self.titulo = titulo

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        self.canv.folha_atual = self.titulo


_ESTILO_SECAO = ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=_TITULO)
_ESTILO_ITEM = ParagraphStyle("item", fontName="Helvetica", fontSize=12, leading=15, textColor=_TEXTO)
_ESTILO_VAZIO = ParagraphStyle("vazio", fontName="Helvetica", fontSize=12, leading=16, textColor=_APOIO)
_ESTILO_ASSINATURA = ParagraphStyle("assinatura", fontName="Helvetica", fontSize=12, leading=16, textColor=_TEXTO)


def _tabela(linhas: list[LinhaFolha], largura: float, cabecalho: str) -> Table:
    dados = [[cabecalho, "Quantidade"]] + [
        [Paragraph(l.produto, _ESTILO_ITEM), formatar_quantidade(l.quantidade, l.unidade)] for l in linhas
    ]
    tabela = Table(dados, colWidths=[largura * 0.68, largura * 0.32], repeatRows=1)
    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), _APOIO),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, _TITULO),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (1, 1), (1, -1), 13),
        ("TEXTCOLOR", (1, 1), (1, -1), _TITULO),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
    ]
    estilo += [("BACKGROUND", (0, i), (-1, i), _ZEBRA) for i in range(2, len(dados), 2)]
    tabela.setStyle(TableStyle(estilo))
    return tabela


def _assinaturas() -> KeepTogether:
    linha = "_" * 42
    return KeepTogether([
        Spacer(1, 14 * mm),
        Paragraph(f"Conferido por: {linha}", _ESTILO_ASSINATURA),
        Spacer(1, 10 * mm),
        Paragraph(f"Recebido por: {linha}", _ESTILO_ASSINATURA),
    ])


def gerar_pdf(impressao: RomaneioImpressao, impresso_em: datetime | None = None) -> bytes:
    """PDF A4: folha de carga e uma folha (ou mais) por loja, sem nunca juntar duas lojas na mesma página."""
    impresso = (impresso_em or datetime.now(FUSO)).astimezone(FUSO)
    buffer = BytesIO()
    margem = 18 * mm
    topo = 42 * mm
    largura, altura = A4

    def cabecalho(canvas, doc):
        titulo = getattr(canvas, "folha_atual", "")
        canvas.saveState()
        canvas.setFillColor(_APOIO)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(margem, altura - 14 * mm, f"Frescor · {impressao.central} · Romaneio aprovado")
        canvas.drawRightString(largura - margem, altura - 14 * mm, f"Página {doc.page}")
        canvas.setFillColor(_TITULO)
        canvas.setFont("Helvetica-Bold", 22)
        canvas.drawString(margem, altura - 24 * mm, titulo if titulo == TITULO_CARGA else f"Loja: {titulo}")
        canvas.setFillColor(_TEXTO)
        canvas.setFont("Helvetica", 11)
        canvas.drawString(margem, altura - 31 * mm,
                          f"Entrega: {_data(impressao.data_entrega)}   ·   Produção: {impressao.data_producao:%d/%m/%Y}")
        canvas.setFillColor(_APOIO)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(margem, altura - 36 * mm, f"Impresso em {impresso:%d/%m/%Y às %H:%M}")
        canvas.setStrokeColor(_LINHA)
        canvas.line(margem, altura - 38 * mm, largura - margem, altura - 38 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=margem, rightMargin=margem, topMargin=topo, bottomMargin=margem,
        title=f"Romaneio {impressao.data_entrega:%d/%m/%Y}", author="Frescor",
    )
    quadro = Frame(margem, margem, largura - 2 * margem, altura - topo - margem, id="corpo")
    doc.addPageTemplates([PageTemplate(id="folha", frames=[quadro], onPageEnd=cabecalho)])
    largura_util = quadro._width

    historia: list = [_InicioFolha(TITULO_CARGA)]
    if impressao.carga:
        historia.append(_tabela(impressao.carga, largura_util, "Produto (total da carga)"))
    else:
        historia.append(Paragraph("Nenhum produto a carregar para as lojas escolhidas.", _ESTILO_VAZIO))
    historia += [Spacer(1, 8 * mm), Paragraph(f"Lojas desta carga ({len(impressao.lojas)})", _ESTILO_SECAO),
                 Spacer(1, 2 * mm)]
    historia += [Paragraph(folha.loja, _ESTILO_ITEM) for folha in impressao.lojas]
    historia.append(_assinaturas())

    for folha in impressao.lojas:
        historia += [PageBreak(), _InicioFolha(folha.loja)]  # cada loja em página nova
        if folha.itens:
            historia.append(_tabela(folha.itens, largura_util, "Produto"))
        else:
            historia.append(Paragraph("Nenhum produto nesta entrega.", _ESTILO_VAZIO))
        historia.append(_assinaturas())
    doc.build(historia)
    return buffer.getvalue()
