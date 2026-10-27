"""
Impressão da ordem de produção aprovada em PDF, uma folha por setor
(Fase 4 / N9b, D67).

Regras:
- Só ordem APROVADA imprime (rascunho muda; imprimir antes da aprovação
  mandaria para a produção um número que ainda pode mudar) ->
  `OrdemNaoAprovada` (a rota responde 409).
- Uma folha por setor: cada setor começa em página nova e nunca divide a
  folha com outro (se não couber numa página, continua na seguinte, com o
  mesmo cabeçalho do setor). Produto sem setor, com setor inativo ou de
  outra central sai na folha "Sem setor", sempre a última.
- O gestor escolhe os setores (`setores`): None = todos os que têm produto
  na ordem; uma lista = esses, na ordem de exibição, mesmo que algum não
  tenha produto (a folha diz isso). Setor que não é ativo desta central ->
  `OrdemInvalida` (422).
- Só produtos PRODUZIDOS (é a folha da produção; os distribuídos vão para o
  romaneio, Fase 5). Loja com quantidade final 0 e produto com total 0 não
  saem.
- Cada folha: central, setor, data de produção e de entrega, hora da
  impressão (São Paulo); por produto, a unidade e o total a produzir em
  destaque e, abaixo, a quantidade de cada loja.

`negocio_id` e `central_producao_id` vêm do gestor autenticado; ordem de
outra central ou negócio -> `OrdemNaoEncontrada` (404).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
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
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida
from app.models.setor_producao import SetorProducao
from app.services.producao_service import OrdemInvalida, OrdemNaoEncontrada

SEM_SETOR = "sem"
NOME_SEM_SETOR = "Sem setor"
FUSO = ZoneInfo("America/Sao_Paulo")
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# Cores da skill Frescor (texto, títulos, linhas e zebra).
_TEXTO = colors.HexColor("#15212B")
_TITULO = colors.HexColor("#1B2B3A")
_APOIO = colors.HexColor("#56636D")
_LINHA = colors.HexColor("#D3DEDA")
_ZEBRA = colors.HexColor("#EEF3F1")


class OrdemNaoAprovada(ValueError):
    """Só a ordem aprovada pode ser impressa."""


@dataclass
class LojaFolha:
    loja: str
    quantidade: Decimal


@dataclass
class ProdutoFolha:
    nome: str
    unidade: str
    total: Decimal
    lojas: list[LojaFolha] = field(default_factory=list)


@dataclass
class Folha:
    setor: str
    produtos: list[ProdutoFolha] = field(default_factory=list)


@dataclass
class OrdemImpressao:
    central: str
    data_producao: date
    data_entrega: date
    folhas: list[Folha]


def setores_da_central(db: Session, negocio_id: int, central_producao_id: int) -> list[SetorProducao]:
    return (
        db.query(SetorProducao)
        .filter(SetorProducao.negocio_id == negocio_id, SetorProducao.central_producao_id == central_producao_id)
        .order_by(SetorProducao.ordem, SetorProducao.nome, SetorProducao.id)
        .all()
    )


def montar_impressao(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    ordem_id: int,
    setores: list[int | str] | None = None,
) -> OrdemImpressao:
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
    if ordem.status != StatusOrdemProducao.APROVADA:
        raise OrdemNaoAprovada("Só a ordem aprovada pode ser impressa. Aprove a ordem antes de imprimir.")

    ativos = [s for s in setores_da_central(db, negocio_id, central_producao_id) if s.ativo]
    por_id = {s.id: s for s in ativos}
    if setores is not None:
        desconhecidos = [s for s in setores if s != SEM_SETOR and s not in por_id]
        if desconhecidos or not setores:
            raise OrdemInvalida("Setor não encontrado nesta central. Escolha os setores da lista.")

    central = db.query(CentralProducao.nome).filter(
        CentralProducao.negocio_id == negocio_id, CentralProducao.id == central_producao_id
    ).scalar()
    linhas = (
        db.query(OrdemProducaoLinha, OrdemProducaoItem, Produto, Loja)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(Produto, Produto.id == OrdemProducaoItem.produto_id)
        .join(Loja, Loja.id == OrdemProducaoLinha.loja_id)
        .filter(
            OrdemProducaoItem.ordem_id == ordem.id,
            OrdemProducaoItem.negocio_id == negocio_id,
            OrdemProducaoLinha.negocio_id == negocio_id,
            OrdemProducaoItem.tipo_abastecimento == TipoAbastecimento.PRODUZIDO,
        )
        .order_by(Produto.codigo, Produto.nome, Produto.id, Loja.codigo, Loja.nome, Loja.id)
        .all()
    )

    produtos_por_setor: dict[int | str, dict[int, ProdutoFolha]] = {}
    for linha, item, produto, loja in linhas:
        quantidade = Decimal(linha.quantidade_final or 0)
        if quantidade <= 0:
            continue
        chave = produto.setor_producao_id if produto.setor_producao_id in por_id else SEM_SETOR
        nome = f"{produto.codigo} · {produto.nome}" if produto.codigo else produto.nome
        unidade = "kg" if item.unidade == UnidadeMedida.KG else "un"
        folha = produtos_por_setor.setdefault(chave, {})
        p = folha.setdefault(produto.id, ProdutoFolha(nome=nome, unidade=unidade, total=Decimal(0)))
        p.total += quantidade
        p.lojas.append(LojaFolha(loja=f"{loja.codigo} · {loja.nome}" if loja.codigo else loja.nome,
                                 quantidade=quantidade))

    ordem_chaves: list[int | str] = [s.id for s in ativos] + [SEM_SETOR]
    if setores is None:
        escolhidas = [k for k in ordem_chaves if k in produtos_por_setor]
    else:
        escolhidas = [k for k in ordem_chaves if k in setores]
    folhas = [
        Folha(
            setor=NOME_SEM_SETOR if k == SEM_SETOR else por_id[k].nome,
            produtos=list(produtos_por_setor.get(k, {}).values()),
        )
        for k in escolhidas
    ]
    if not folhas:  # "todos" numa ordem sem nada a produzir
        folhas = [Folha(setor="Todos os setores")]
    return OrdemImpressao(central=central, data_producao=ordem.data_producao, data_entrega=ordem.data_entrega,
                          folhas=folhas)


# ---- PDF ----

def formatar_quantidade(valor: Decimal, unidade: str) -> str:
    """Decimal -> pt-BR com a unidade: 54.4 kg -> "54,4 kg"; 1240 un -> "1.240 un"."""
    texto = f"{valor:,.3f}".rstrip("0").rstrip(".")
    return f"{texto.replace(',', '#').replace('.', ',').replace('#', '.')} {unidade}"


def _data(d: date) -> str:
    return f"{DIAS[d.weekday()]}, {d:%d/%m/%Y}"


class _InicioSetor(Flowable):
    """Marca, sem ocupar espaço, o setor da página (o cabeçalho é desenhado no fim da página)."""

    def __init__(self, setor: str):
        super().__init__()
        self.setor = setor

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        self.canv.setor_atual = self.setor


_ESTILO_PRODUTO = ParagraphStyle("produto", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=_TITULO)
_ESTILO_TOTAL = ParagraphStyle("total", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=_TITULO,
                               alignment=TA_RIGHT)
_ESTILO_ROTULO = ParagraphStyle("rotulo", fontName="Helvetica", fontSize=10, leading=12, textColor=_APOIO,
                                alignment=TA_RIGHT)
_ESTILO_VAZIO = ParagraphStyle("vazio", fontName="Helvetica", fontSize=12, leading=16, textColor=_APOIO)
_ESTILO_LOJA = ParagraphStyle("loja", fontName="Helvetica", fontSize=11, leading=14, textColor=_TEXTO)


def _bloco_produto(p: ProdutoFolha, largura: float) -> KeepTogether:
    cabecalho = Table(
        [[Paragraph(p.nome, _ESTILO_PRODUTO),
          [Paragraph("Produzir", _ESTILO_ROTULO), Paragraph(formatar_quantidade(p.total, p.unidade), _ESTILO_TOTAL)]]],
        colWidths=[largura * 0.62, largura * 0.38],
    )
    cabecalho.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, _TITULO),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    lojas = Table(
        [[Paragraph(l.loja, _ESTILO_LOJA), formatar_quantidade(l.quantidade, p.unidade)] for l in p.lojas],
        colWidths=[largura * 0.62, largura * 0.38],
    )
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (1, 0), (1, -1), 11),
        ("TEXTCOLOR", (1, 0), (1, -1), _TEXTO),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, _LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
    ]
    estilo += [("BACKGROUND", (0, i), (-1, i), _ZEBRA) for i in range(1, len(p.lojas), 2)]
    lojas.setStyle(TableStyle(estilo))
    return KeepTogether([cabecalho, Spacer(1, 2 * mm), lojas, Spacer(1, 8 * mm)])


def gerar_pdf(impressao: OrdemImpressao, impresso_em: datetime | None = None) -> bytes:
    """PDF A4, uma folha (ou mais) por setor, sem nunca juntar dois setores na mesma página."""
    impresso = (impresso_em or datetime.now(FUSO)).astimezone(FUSO)
    buffer = BytesIO()
    margem = 18 * mm
    topo = 42 * mm
    largura, altura = A4

    def cabecalho(canvas, doc):
        setor = getattr(canvas, "setor_atual", "")
        canvas.saveState()
        canvas.setFillColor(_APOIO)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(margem, altura - 14 * mm, f"Frescor · {impressao.central} · Ordem de produção aprovada")
        canvas.drawRightString(largura - margem, altura - 14 * mm, f"Página {doc.page}")
        canvas.setFillColor(_TITULO)
        canvas.setFont("Helvetica-Bold", 22)
        canvas.drawString(margem, altura - 24 * mm, f"Setor: {setor}")
        canvas.setFillColor(_TEXTO)
        canvas.setFont("Helvetica", 11)
        canvas.drawString(margem, altura - 31 * mm,
                          f"Produção: {_data(impressao.data_producao)}   ·   Entrega: {impressao.data_entrega:%d/%m/%Y}")
        canvas.setFillColor(_APOIO)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(margem, altura - 36 * mm, f"Impresso em {impresso:%d/%m/%Y às %H:%M}")
        canvas.setStrokeColor(_LINHA)
        canvas.line(margem, altura - 38 * mm, largura - margem, altura - 38 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=margem, rightMargin=margem, topMargin=topo, bottomMargin=margem,
        title=f"Ordem de produção {impressao.data_producao:%d/%m/%Y}", author="Frescor",
    )
    quadro = Frame(margem, margem, largura - 2 * margem, altura - topo - margem, id="corpo")
    doc.addPageTemplates([PageTemplate(id="folha", frames=[quadro], onPageEnd=cabecalho)])

    historia: list = []
    for indice, folha in enumerate(impressao.folhas):
        if indice > 0:
            historia.append(PageBreak())  # cada setor em página nova
        historia.append(_InicioSetor(folha.setor))
        if not folha.produtos:
            historia.append(Paragraph("Nenhum produto deste setor a produzir nesta ordem.", _ESTILO_VAZIO))
        for produto in folha.produtos:
            historia.append(_bloco_produto(produto, quadro._width))
    doc.build(historia)
    return buffer.getvalue()
