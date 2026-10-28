"""
Distribuição (Fase 5 / E4): produção real, romaneio e saída.

Fluxo (D68–D71, D76): ordem aprovada (Fase 4) -> o gestor registra a
produção real de cada produto (D69; no distribuído, o disponível) -> gera o
romaneio em `rascunho`, com a sugestão por loja + produto (rateio da D70
quando falta) -> ajusta as finais -> aprova (trava) -> registra a saída de
cada loja (uma, várias ou todas as que faltam). O recebimento pela loja é o
E5.

Regras:
- Romaneio só de ordem programada APROVADA; um por ordem (D68). Linha da
  ordem com final 0 fica fora. Loja com final > 0 que o rateio zerou
  (escassez) continua no romaneio com sugerida 0: o gestor vê quem ficou
  sem.
- Gerar exige a produção registrada em todos os produtos da ordem (D69).
  Gerar de novo SUBSTITUI o rascunho (apaga e grava; perde os ajustes, como
  a D58). Romaneio aprovado não é gerado de novo, editado nem apagado.
- Corrigir a produção com o romaneio em rascunho NÃO refaz o rascunho
  sozinho (apagaria os ajustes sem aviso): o resultado diz que o rascunho
  ficou desatualizado, e a aprovação confere as finais contra a produção
  atual. Com o romaneio aprovado, a produção não muda mais.
- Aprovar: Σ final de cada produto <= disponível (D71) e lojas ainda ativas
  na central (como a D57).
- Saída: só de romaneio aprovado; a entrega precisa estar aguardando saída
  (registrar de novo é recusado). Tudo ou nada: se uma das entregas pedidas
  não pode sair, nenhuma sai. Não se desfaz (D76).
- Tudo filtrado pelo negócio e pela central do gestor (vêm do token, regra
  de ouro 1); ordem, romaneio, item ou entrega de outra central ou negócio
  responde como inexistente. Operações que gravam esperam uma pela outra na
  mesma central (trava `pg_advisory_xact_lock`).

Exceções (a API do E6 as traduz): `NaoEncontrado` (404),
`OperacaoNaoPermitida` (409: a situação não permite), `DistribuicaoInvalida`
(422: regra ferida).
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.loja import Loja
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao, TipoOrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.produto import Produto, UnidadeMedida
from app.models.romaneio import Romaneio, StatusRomaneio
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega
from app.models.romaneio_item import RomaneioItem
from app.services.distribuicao_calculo import AVISO_ESCASSEZ, AVISO_SOBRA, lojas_para_rateio, ratear

CASAS = Decimal("0.001")
# Trava por central (3001 previsão, 3002 ordem).
_TRAVA_DISTRIBUICAO = 3003


class NaoEncontrado(LookupError):
    """Ordem, romaneio, item ou entrega inexistente, ou de outra central/negócio."""


class OperacaoNaoPermitida(ValueError):
    """A situação atual não permite (ordem em rascunho, romaneio aprovado, saída repetida...)."""


class DistribuicaoInvalida(ValueError):
    """Pedido que fere uma regra (mensagem para o gestor)."""


@dataclass(frozen=True)
class ResultadoProducao:
    itens_registrados: int
    romaneio_desatualizado: bool  # havia rascunho: gere de novo para a sugestão usar a produção nova


@dataclass(frozen=True)
class ResultadoGeracaoRomaneio:
    romaneio_id: int
    ordem_id: int
    entregas: int
    itens: int
    produtos_com_escassez: tuple[int, ...]
    produtos_com_sobra: tuple[int, ...]
    substituiu_rascunho: bool


@dataclass(frozen=True)
class _LinhaRateio:
    loja_id: int
    codigo_loja: str | None
    quantidade_sugerida: Decimal | None
    quantidade_final: Decimal
    linha_id: int


def _travar(db: Session, central_producao_id: int) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": _TRAVA_DISTRIBUICAO, "b": central_producao_id})


def _validar_quantidade(valor, unidade: UnidadeMedida, rotulo: str) -> Decimal:
    quantidade = Decimal(valor)
    if quantidade < 0:
        raise DistribuicaoInvalida(f"{rotulo}: a quantidade não pode ser negativa.")
    if unidade == UnidadeMedida.UN and quantidade != quantidade.to_integral_value():
        raise DistribuicaoInvalida(f"{rotulo}: produto vendido por unidade, informe um número inteiro.")
    if quantidade != quantidade.quantize(CASAS):
        raise DistribuicaoInvalida(f"{rotulo}: informe no máximo 3 casas decimais.")
    return quantidade


def _buscar_ordem(db: Session, negocio_id: int, central_producao_id: int, ordem_id: int) -> OrdemProducao:
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
        raise NaoEncontrado("Ordem de produção não encontrada.")
    return ordem


def _exigir_ordem_aprovada(ordem: OrdemProducao) -> None:
    if ordem.tipo != TipoOrdemProducao.PROGRAMADA or ordem.status != StatusOrdemProducao.APROVADA:
        raise OperacaoNaoPermitida("A ordem de produção ainda não foi aprovada: aprove a ordem antes.")


def _romaneio_da_ordem(db: Session, negocio_id: int, ordem_id: int) -> Romaneio | None:
    return (
        db.query(Romaneio)
        .filter(Romaneio.negocio_id == negocio_id, Romaneio.ordem_id == ordem_id)
        .one_or_none()
    )


def _buscar_romaneio(db: Session, negocio_id: int, central_producao_id: int, romaneio_id: int) -> Romaneio:
    romaneio = (
        db.query(Romaneio)
        .filter(
            Romaneio.negocio_id == negocio_id,
            Romaneio.central_producao_id == central_producao_id,
            Romaneio.id == romaneio_id,
        )
        .one_or_none()
    )
    if romaneio is None:
        raise NaoEncontrado("Romaneio não encontrado.")
    return romaneio


def _nomes_produtos(db: Session, negocio_id: int, produto_ids) -> list[str]:
    return sorted(
        nome for (nome,) in db.query(Produto.nome).filter(Produto.negocio_id == negocio_id,
                                                          Produto.id.in_(list(produto_ids)))
    )


# ---------------------------------------------------------------- produção real (D69)

def registrar_producao(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    ordem_id: int,
    quantidades: Mapping[int, Decimal],
    usuario_id: int,
    agora: datetime | None = None,
) -> ResultadoProducao:
    """Grava a produção real (ou o disponível do distribuído) por item da ordem: {item_id: quantidade}."""
    if not quantidades:
        raise DistribuicaoInvalida("Informe a produção de pelo menos um produto.")
    try:
        _travar(db, central_producao_id)
        ordem = _buscar_ordem(db, negocio_id, central_producao_id, ordem_id)
        _exigir_ordem_aprovada(ordem)
        romaneio = _romaneio_da_ordem(db, negocio_id, ordem.id)
        if romaneio is not None and romaneio.status == StatusRomaneio.APROVADO:
            raise OperacaoNaoPermitida("O romaneio desta ordem já foi aprovado: a produção não pode mais mudar.")
        itens = {
            item.id: item
            for item in db.query(OrdemProducaoItem).filter(
                OrdemProducaoItem.negocio_id == negocio_id, OrdemProducaoItem.ordem_id == ordem.id,
                OrdemProducaoItem.id.in_(list(quantidades)),
            )
        }
        de_fora = set(quantidades) - set(itens)
        if de_fora:
            raise NaoEncontrado("Produto não encontrado nesta ordem.")
        quando = agora or datetime.utcnow()
        nomes = dict(db.query(Produto.id, Produto.nome).filter(
            Produto.negocio_id == negocio_id, Produto.id.in_([i.produto_id for i in itens.values()])))
        for item_id, valor in quantidades.items():
            item = itens[item_id]
            item.quantidade_produzida = _validar_quantidade(valor, item.unidade, nomes.get(item.produto_id, "Produto"))
            item.producao_registrada_em = quando
            item.producao_registrada_por_usuario_id = usuario_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ResultadoProducao(itens_registrados=len(quantidades), romaneio_desatualizado=romaneio is not None)


# ---------------------------------------------------------------- romaneio (D68, D70, D71)

def gerar_romaneio(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    ordem_id: int,
    usuario_id: int | None,
    agora: datetime | None = None,
) -> ResultadoGeracaoRomaneio:
    """Gera (ou gera de novo, se rascunho) o romaneio da ordem aprovada, com a sugestão do rateio."""
    try:
        _travar(db, central_producao_id)
        ordem = _buscar_ordem(db, negocio_id, central_producao_id, ordem_id)
        _exigir_ordem_aprovada(ordem)
        existente = _romaneio_da_ordem(db, negocio_id, ordem.id)
        if existente is not None and existente.status == StatusRomaneio.APROVADO:
            raise OperacaoNaoPermitida("O romaneio desta ordem já foi aprovado e não pode ser gerado de novo.")

        itens = (
            db.query(OrdemProducaoItem)
            .filter(OrdemProducaoItem.negocio_id == negocio_id, OrdemProducaoItem.ordem_id == ordem.id)
            .order_by(OrdemProducaoItem.id)
            .all()
        )
        sem_producao = [i.produto_id for i in itens if i.quantidade_produzida is None]
        if sem_producao:
            nomes = _nomes_produtos(db, negocio_id, sem_producao)
            raise DistribuicaoInvalida(
                f"Registre a produção de {len(nomes)} produto(s) antes de gerar o romaneio: {', '.join(nomes)}."
            )
        linhas_por_item: dict[int, list[_LinhaRateio]] = defaultdict(list)
        for linha, codigo in (
            db.query(OrdemProducaoLinha, Loja.codigo)
            .join(Loja, Loja.id == OrdemProducaoLinha.loja_id)
            .filter(OrdemProducaoLinha.negocio_id == negocio_id,
                    OrdemProducaoLinha.item_id.in_([i.id for i in itens]))
        ):
            # D68: linha com final 0 (ou sem final) fica fora do romaneio.
            if linha.quantidade_final is not None and linha.quantidade_final > 0:
                linhas_por_item[linha.item_id].append(_LinhaRateio(
                    linha.loja_id, codigo, linha.quantidade_sugerida, Decimal(linha.quantidade_final), linha.id))

        substituiu = False
        if existente is not None:
            db.delete(existente)
            db.flush()
            substituiu = True
        quando = agora or datetime.utcnow()
        romaneio = Romaneio(
            negocio_id=negocio_id, central_producao_id=central_producao_id, ordem_id=ordem.id,
            data_entrega=ordem.data_entrega, status=StatusRomaneio.RASCUNHO, gerado_em=quando,
            gerado_por_usuario_id=usuario_id,
        )
        db.add(romaneio)
        db.flush()

        entregas: dict[int, RomaneioEntrega] = {}
        n_itens = 0
        escassez, sobra = [], []
        for item in itens:
            linhas = linhas_por_item.get(item.id, [])
            if not linhas:
                continue
            resultado = ratear(Decimal(item.quantidade_produzida), item.unidade, lojas_para_rateio(linhas))
            if AVISO_ESCASSEZ in resultado.avisos:
                escassez.append(item.produto_id)
            if AVISO_SOBRA in resultado.avisos:
                sobra.append(item.produto_id)
            for linha in linhas:
                entrega = entregas.get(linha.loja_id)
                if entrega is None:
                    entrega = RomaneioEntrega(negocio_id=negocio_id, romaneio_id=romaneio.id, loja_id=linha.loja_id)
                    db.add(entrega)
                    db.flush()
                    entregas[linha.loja_id] = entrega
                sugerida = resultado.sugeridas[linha.loja_id]
                db.add(RomaneioItem(
                    negocio_id=negocio_id, entrega_id=entrega.id, produto_id=item.produto_id,
                    ordem_linha_id=linha.linha_id, unidade=item.unidade,
                    quantidade_sugerida=sugerida, quantidade_final=sugerida,
                ))
                n_itens += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ResultadoGeracaoRomaneio(
        romaneio_id=romaneio.id, ordem_id=ordem.id, entregas=len(entregas), itens=n_itens,
        produtos_com_escassez=tuple(escassez), produtos_com_sobra=tuple(sobra), substituiu_rascunho=substituiu,
    )


def editar_item(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    romaneio_id: int,
    item_id: int,
    quantidade_final: Decimal,
    usuario_id: int,
    motivo: str | None = None,
    agora: datetime | None = None,
) -> RomaneioItem:
    """Muda a final de uma loja + produto (só em rascunho). O item tem de ser do romaneio pedido."""
    encontrado = (
        db.query(RomaneioItem, Romaneio)
        .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
        .join(Romaneio, Romaneio.id == RomaneioEntrega.romaneio_id)
        .filter(
            RomaneioItem.id == item_id,
            RomaneioItem.negocio_id == negocio_id,
            Romaneio.negocio_id == negocio_id,
            Romaneio.central_producao_id == central_producao_id,
            Romaneio.id == romaneio_id,
        )
        .one_or_none()
    )
    if encontrado is None:
        raise NaoEncontrado("Item do romaneio não encontrado.")
    item, romaneio = encontrado
    if romaneio.status != StatusRomaneio.RASCUNHO:
        raise OperacaoNaoPermitida("O romaneio já foi aprovado e não pode ser alterado.")
    quantidade = _validar_quantidade(quantidade_final, item.unidade, "Quantidade")
    if motivo is not None and len(motivo) > 255:
        raise DistribuicaoInvalida("O motivo pode ter no máximo 255 caracteres.")
    item.quantidade_final = quantidade
    item.editado_em = agora or datetime.utcnow()
    item.editado_por_usuario_id = usuario_id
    item.motivo_edicao = motivo or None
    db.commit()
    return item


def aprovar_romaneio(
    db: Session, negocio_id: int, central_producao_id: int, romaneio_id: int, usuario_id: int,
    agora: datetime | None = None,
) -> Romaneio:
    """Rascunho -> aprovado. Σ final por produto <= disponível (D71) e lojas ativas na central."""
    try:
        _travar(db, central_producao_id)
        romaneio = _buscar_romaneio(db, negocio_id, central_producao_id, romaneio_id)
        if romaneio.status != StatusRomaneio.RASCUNHO:
            raise OperacaoNaoPermitida("O romaneio já foi aprovado.")
        finais: dict[int, Decimal] = defaultdict(Decimal)
        lojas = set()
        for produto_id, loja_id, final in (
            db.query(RomaneioItem.produto_id, RomaneioEntrega.loja_id, RomaneioItem.quantidade_final)
            .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
            .filter(RomaneioEntrega.romaneio_id == romaneio.id, RomaneioItem.negocio_id == negocio_id)
        ):
            finais[produto_id] += Decimal(final)
            lojas.add(loja_id)
        disponivel = dict(
            db.query(OrdemProducaoItem.produto_id, OrdemProducaoItem.quantidade_produzida).filter(
                OrdemProducaoItem.negocio_id == negocio_id, OrdemProducaoItem.ordem_id == romaneio.ordem_id)
        )
        acima = [p for p, total in finais.items() if total > Decimal(disponivel.get(p) or 0)]
        if acima:
            nomes = _nomes_produtos(db, negocio_id, acima)
            raise DistribuicaoInvalida(
                "Não dá para mandar mais do que foi produzido: " + ", ".join(nomes)
                + ". Corrija a produção registrada ou as quantidades das lojas."
            )
        da_central = {
            loja_id for (loja_id,) in db.query(Loja.id).filter(
                Loja.negocio_id == negocio_id, Loja.central_producao_id == central_producao_id, Loja.ativo.is_(True))
        }
        fora = sorted(lojas - da_central)
        if fora:
            nomes = sorted(n for (n,) in db.query(Loja.nome).filter(Loja.negocio_id == negocio_id, Loja.id.in_(fora)))
            raise DistribuicaoInvalida(
                f"Loja(s) que não são mais ativas nesta central: {', '.join(nomes)}. Gere o romaneio de novo."
            )
        romaneio.status = StatusRomaneio.APROVADO
        romaneio.aprovado_em = agora or datetime.utcnow()
        romaneio.aprovado_por_usuario_id = usuario_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return romaneio


def apagar_romaneio(db: Session, negocio_id: int, central_producao_id: int, romaneio_id: int) -> None:
    """Apaga um rascunho (entregas e itens em cascata). Aprovado não é apagado."""
    try:
        _travar(db, central_producao_id)
        romaneio = _buscar_romaneio(db, negocio_id, central_producao_id, romaneio_id)
        if romaneio.status != StatusRomaneio.RASCUNHO:
            raise OperacaoNaoPermitida("O romaneio já foi aprovado e não pode ser apagado.")
        db.delete(romaneio)
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------- saída (D76)

def registrar_saida(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    romaneio_id: int,
    usuario_id: int,
    entrega_ids: Sequence[int] | None = None,
    agora: datetime | None = None,
) -> list[RomaneioEntrega]:
    """Registra a saída das entregas pedidas (None = todas as que ainda aguardam saída). Tudo ou nada."""
    try:
        _travar(db, central_producao_id)
        romaneio = _buscar_romaneio(db, negocio_id, central_producao_id, romaneio_id)
        if romaneio.status != StatusRomaneio.APROVADO:
            raise OperacaoNaoPermitida("Aprove o romaneio antes de registrar a saída.")
        consulta = db.query(RomaneioEntrega).filter(
            RomaneioEntrega.negocio_id == negocio_id, RomaneioEntrega.romaneio_id == romaneio.id)
        if entrega_ids is None:
            entregas = consulta.filter(RomaneioEntrega.situacao == SituacaoEntrega.AGUARDANDO_SAIDA).all()
            if not entregas:
                raise OperacaoNaoPermitida("Todas as entregas deste romaneio já saíram.")
        else:
            pedidas = set(entrega_ids)
            if not pedidas:
                raise DistribuicaoInvalida("Escolha pelo menos uma loja.")
            entregas = consulta.filter(RomaneioEntrega.id.in_(list(pedidas))).all()
            if len(entregas) != len(pedidas):
                raise NaoEncontrado("Entrega não encontrada neste romaneio.")
            ja_sairam = [e for e in entregas if e.situacao != SituacaoEntrega.AGUARDANDO_SAIDA]
            if ja_sairam:
                nomes = sorted(n for (n,) in db.query(Loja.nome).filter(
                    Loja.negocio_id == negocio_id, Loja.id.in_([e.loja_id for e in ja_sairam])))
                raise OperacaoNaoPermitida(f"A saída já foi registrada para: {', '.join(nomes)}.")
        quando = agora or datetime.utcnow()
        for entrega in entregas:
            entrega.situacao = SituacaoEntrega.EXPEDIDA
            entrega.expedido_em = quando
            entrega.expedido_por_usuario_id = usuario_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return entregas
