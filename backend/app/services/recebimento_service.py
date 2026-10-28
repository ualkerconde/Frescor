"""
Recebimento na loja (Fase 5 / E5): o operador confirma, pelo app, o que
chegou de cada entrega do romaneio (D77, D78), e a situação de leitura de
cada entrega para a loja e para o gestor (D79, D85, D89).

Regras:
- Só entregas da própria loja (a loja vem do token, regra de ouro 1),
  de romaneio aprovado e com a saída registrada (D77). Entrega de outra
  loja ou de outro negócio responde como inexistente.
- "Recebi tudo certo": recebida = final (a quantidade expedida, D76) em
  todos os itens. "Recebi com diferença": o operador informa a recebida
  dos itens que divergem; os que ele não informa ficam iguais à final.
  Recebida diferente da final exige motivo (D78); `outro` exige o texto.
  Recebida igual à final não guarda motivo.
- Uma vez só: entrega já confirmada não muda (um erro se corrige na
  próxima contagem, D77).
- Prazo (D85): até o fim do dia SEGUINTE ao da entrega, na hora local da
  loja. Depois, a entrega fica fechada como "sem confirmação".
- O recebimento não grava em `estoque_atual` nem em `historico_contagens`
  (D79): a contagem continua sendo a verdade do estoque. Ele entra só no
  trânsito da necessidade (`producao_service.provedor_transito_ordens`).

Situação de leitura (não é gravada; D79, D85):
- `aguardando_saida`: a central ainda não registrou a saída;
- `a_caminho`: saiu e o dia de entrega não terminou;
- `sem_confirmacao`: saiu, o dia de entrega terminou e a loja não
  confirmou. Conta como recebida pela final do romaneio, presumida no dia
  de entrega, antes da contagem do fechamento (D89). Ainda aceita
  confirmação até o fim do dia seguinte (`pode_confirmar`);
- `recebida`: confirmada no dia de entrega;
- `confirmada_com_atraso`: confirmada no dia seguinte. A recebida
  substitui a presumida, mas a chegada continua presumida no dia de entrega
  (D89): o número da necessidade não muda, só a marca.

Fuso: não há fuso por loja no banco; vale o padrão (D44).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.produto import Produto, UnidadeMedida
from app.models.romaneio import Romaneio, StatusRomaneio
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega
from app.models.romaneio_item import MotivoDivergencia, RomaneioItem
from app.services.necessidade_calculo import FUSO_PADRAO

CASAS = Decimal("0.001")
# D85: a loja confirma até o fim do dia seguinte ao da entrega.
DIAS_TOLERANCIA_CONFIRMACAO = 1

SITUACAO_AGUARDANDO_SAIDA = "aguardando_saida"
SITUACAO_A_CAMINHO = "a_caminho"
SITUACAO_SEM_CONFIRMACAO = "sem_confirmacao"
SITUACAO_RECEBIDA = "recebida"
SITUACAO_CONFIRMADA_COM_ATRASO = "confirmada_com_atraso"

_UTC = timezone.utc


class EntregaNaoEncontrada(LookupError):
    """Entrega ou item inexistente, de outra loja ou de outro negócio (404)."""


class RecebimentoNaoPermitido(ValueError):
    """A situação não permite confirmar: sem saída, já confirmada, prazo encerrado (409)."""


class RecebimentoInvalido(ValueError):
    """Quantidade ou motivo que fere uma regra (422)."""


@dataclass(frozen=True)
class DiferencaItem:
    """O que o operador informa num item que chegou diferente."""

    quantidade_recebida: Decimal
    motivo: MotivoDivergencia | str | None = None
    observacao: str | None = None


@dataclass(frozen=True)
class SituacaoLeitura:
    situacao: str
    # Ainda dá para confirmar (expedida e dentro do prazo da D85).
    pode_confirmar: bool
    # Algum item recebido diferente da final.
    com_diferenca: bool


@dataclass(frozen=True)
class ItemEntrega:
    item_id: int
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    quantidade_expedida: Decimal
    quantidade_recebida: Decimal | None
    motivo_divergencia: str | None
    observacao_divergencia: str | None


@dataclass(frozen=True)
class EntregaLoja:
    entrega_id: int
    romaneio_id: int
    loja_id: int
    data_entrega: date
    expedido_em: datetime | None
    recebido_em: datetime | None
    situacao: SituacaoLeitura
    itens: list[ItemEntrega]


def dia_local(momento_utc: datetime, fuso: str = FUSO_PADRAO) -> date:
    """Data local de um momento gravado em UTC sem fuso."""
    return momento_utc.replace(tzinfo=_UTC).astimezone(ZoneInfo(fuso)).date()


def dentro_do_prazo(data_entrega: date, agora_utc: datetime, fuso: str = FUSO_PADRAO) -> bool:
    """D85: até o fim do dia seguinte ao da entrega, na hora local."""
    return dia_local(agora_utc, fuso) <= data_entrega + timedelta(days=DIAS_TOLERANCIA_CONFIRMACAO)


def confirmada_no_prazo(data_entrega: date, recebido_em_utc: datetime, fuso: str = FUSO_PADRAO) -> bool:
    """Confirmada no próprio dia de entrega (hora local); depois disso, "com atraso"."""
    return dia_local(recebido_em_utc, fuso) <= data_entrega


def situacao_entrega(
    situacao: SituacaoEntrega,
    data_entrega: date,
    recebido_em: datetime | None,
    agora_utc: datetime,
    com_diferenca: bool = False,
    fuso: str = FUSO_PADRAO,
) -> SituacaoLeitura:
    """Situação de leitura da entrega (ver o docstring do módulo)."""
    if situacao == SituacaoEntrega.AGUARDANDO_SAIDA:
        return SituacaoLeitura(SITUACAO_AGUARDANDO_SAIDA, False, False)
    if situacao == SituacaoEntrega.RECEBIDA:
        marca = (SITUACAO_RECEBIDA if confirmada_no_prazo(data_entrega, recebido_em, fuso)
                 else SITUACAO_CONFIRMADA_COM_ATRASO)
        return SituacaoLeitura(marca, False, com_diferenca)
    pode = dentro_do_prazo(data_entrega, agora_utc, fuso)
    if dia_local(agora_utc, fuso) <= data_entrega:
        return SituacaoLeitura(SITUACAO_A_CAMINHO, pode, False)
    return SituacaoLeitura(SITUACAO_SEM_CONFIRMACAO, pode, False)


def _quantidade(valor, unidade: UnidadeMedida, rotulo: str) -> Decimal:
    quantidade = Decimal(valor)
    if quantidade < 0:
        raise RecebimentoInvalido(f"{rotulo}: a quantidade não pode ser negativa.")
    if unidade == UnidadeMedida.UN and quantidade != quantidade.to_integral_value():
        raise RecebimentoInvalido(f"{rotulo}: produto vendido por unidade, informe um número inteiro.")
    if quantidade != quantidade.quantize(CASAS):
        raise RecebimentoInvalido(f"{rotulo}: informe no máximo 3 casas decimais.")
    return quantidade


def _motivo(valor) -> MotivoDivergencia | None:
    if valor is None or isinstance(valor, MotivoDivergencia):
        return valor
    try:
        return MotivoDivergencia(valor)
    except ValueError:
        raise RecebimentoInvalido("Motivo inválido: use falta, avaria, a mais ou outro.") from None


def _entregas_da_loja(db: Session, negocio_id: int, loja_id: int):
    """Entregas de romaneios aprovados da loja (consulta base, sempre por negócio e loja)."""
    return (
        db.query(RomaneioEntrega, Romaneio.data_entrega)
        .join(Romaneio, Romaneio.id == RomaneioEntrega.romaneio_id)
        .filter(
            RomaneioEntrega.negocio_id == negocio_id,
            Romaneio.negocio_id == negocio_id,
            RomaneioEntrega.loja_id == loja_id,
            Romaneio.status == StatusRomaneio.APROVADO,
        )
    )


def _itens(db: Session, negocio_id: int, entrega_ids: list[int]) -> dict[int, list[ItemEntrega]]:
    por_entrega: dict[int, list[ItemEntrega]] = {i: [] for i in entrega_ids}
    if not entrega_ids:
        return por_entrega
    for item, codigo, nome in (
        db.query(RomaneioItem, Produto.codigo, Produto.nome)
        .join(Produto, Produto.id == RomaneioItem.produto_id)
        .filter(RomaneioItem.negocio_id == negocio_id, Produto.negocio_id == negocio_id,
                RomaneioItem.entrega_id.in_(entrega_ids))
        .order_by(Produto.codigo, Produto.id)
    ):
        por_entrega[item.entrega_id].append(ItemEntrega(
            item_id=item.id, produto_id=item.produto_id, produto_codigo=codigo, produto_nome=nome,
            unidade=item.unidade.value, quantidade_expedida=Decimal(item.quantidade_final),
            quantidade_recebida=Decimal(item.quantidade_recebida) if item.quantidade_recebida is not None else None,
            motivo_divergencia=item.motivo_divergencia.value if item.motivo_divergencia else None,
            observacao_divergencia=item.observacao_divergencia,
        ))
    return por_entrega


def _montar(entrega: RomaneioEntrega, data_entrega: date, itens: list[ItemEntrega], agora: datetime) -> EntregaLoja:
    diferenca = any(i.quantidade_recebida is not None and i.quantidade_recebida != i.quantidade_expedida
                    for i in itens)
    return EntregaLoja(
        entrega_id=entrega.id, romaneio_id=entrega.romaneio_id, loja_id=entrega.loja_id, data_entrega=data_entrega,
        expedido_em=entrega.expedido_em, recebido_em=entrega.recebido_em,
        situacao=situacao_entrega(entrega.situacao, data_entrega, entrega.recebido_em, agora, diferenca),
        itens=itens,
    )


def listar_pendentes(db: Session, negocio_id: int, loja_id: int, agora: datetime | None = None) -> list[EntregaLoja]:
    """D77: entregas com saída registrada, ainda não confirmadas e dentro do prazo (D85), da mais antiga."""
    agora = agora or datetime.utcnow()
    linhas = [
        (e, d) for e, d in _entregas_da_loja(db, negocio_id, loja_id)
        .filter(RomaneioEntrega.situacao == SituacaoEntrega.EXPEDIDA)
        .order_by(Romaneio.data_entrega, RomaneioEntrega.id)
        if dentro_do_prazo(d, agora)
    ]
    itens = _itens(db, negocio_id, [e.id for e, _ in linhas])
    return [_montar(e, d, itens[e.id], agora) for e, d in linhas]


def detalhar(db: Session, negocio_id: int, loja_id: int, entrega_id: int, agora: datetime | None = None) -> EntregaLoja:
    """Uma entrega da loja (com saída registrada), com os itens."""
    agora = agora or datetime.utcnow()
    encontrado = (
        _entregas_da_loja(db, negocio_id, loja_id)
        .filter(RomaneioEntrega.id == entrega_id, RomaneioEntrega.situacao != SituacaoEntrega.AGUARDANDO_SAIDA)
        .one_or_none()
    )
    if encontrado is None:
        raise EntregaNaoEncontrada("Entrega não encontrada.")
    entrega, data_entrega = encontrado
    return _montar(entrega, data_entrega, _itens(db, negocio_id, [entrega.id])[entrega.id], agora)


def confirmar(
    db: Session,
    negocio_id: int,
    loja_id: int,
    entrega_id: int,
    usuario_id: int,
    diferencas: Mapping[int, DiferencaItem] | None = None,
    agora: datetime | None = None,
) -> EntregaLoja:
    """
    Confirma o recebimento. Sem `diferencas` = "Recebi tudo certo".
    `diferencas` = {item_id: DiferencaItem}; os itens fora dele chegaram iguais à final.
    """
    agora = agora or datetime.utcnow()
    try:
        encontrado = (
            _entregas_da_loja(db, negocio_id, loja_id)
            .filter(RomaneioEntrega.id == entrega_id)
            .with_for_update(of=RomaneioEntrega)
            .one_or_none()
        )
        if encontrado is None:
            raise EntregaNaoEncontrada("Entrega não encontrada.")
        entrega, data_entrega = encontrado
        if entrega.situacao == SituacaoEntrega.AGUARDANDO_SAIDA:
            raise RecebimentoNaoPermitido(
                "A central ainda não registrou a saída desta entrega. Fale com a central.")
        if entrega.situacao == SituacaoEntrega.RECEBIDA:
            raise RecebimentoNaoPermitido("Esta entrega já foi confirmada e não pode ser alterada.")
        if not dentro_do_prazo(data_entrega, agora):
            raise RecebimentoNaoPermitido(
                "O prazo para confirmar esta entrega terminou (até o fim do dia seguinte ao da entrega). "
                "Ela ficou registrada como sem confirmação.")

        itens = {i.id: i for i in db.query(RomaneioItem).filter(
            RomaneioItem.negocio_id == negocio_id, RomaneioItem.entrega_id == entrega.id)}
        diferencas = diferencas or {}
        if set(diferencas) - set(itens):
            raise EntregaNaoEncontrada("Produto não encontrado nesta entrega.")
        nomes = dict(db.query(Produto.id, Produto.nome).filter(
            Produto.negocio_id == negocio_id, Produto.id.in_([i.produto_id for i in itens.values()])))
        for item in itens.values():
            final = Decimal(item.quantidade_final)
            pedido = diferencas.get(item.id)
            if pedido is None:
                item.quantidade_recebida, item.motivo_divergencia, item.observacao_divergencia = final, None, None
                continue
            rotulo = nomes.get(item.produto_id, "Produto")
            recebida = _quantidade(pedido.quantidade_recebida, item.unidade, rotulo)
            motivo = _motivo(pedido.motivo)
            observacao = (pedido.observacao or "").strip() or None
            if observacao is not None and len(observacao) > 255:
                raise RecebimentoInvalido(f"{rotulo}: a observação pode ter no máximo 255 caracteres.")
            if recebida == final:
                motivo = observacao = None
            elif motivo is None:
                raise RecebimentoInvalido(
                    f"{rotulo}: chegou diferente do enviado; informe o motivo (falta, avaria, a mais ou outro).")
            elif motivo == MotivoDivergencia.OUTRO and observacao is None:
                raise RecebimentoInvalido(f"{rotulo}: com o motivo \"outro\", descreva o que aconteceu.")
            item.quantidade_recebida, item.motivo_divergencia, item.observacao_divergencia = recebida, motivo, observacao
        entrega.situacao = SituacaoEntrega.RECEBIDA
        entrega.recebido_em = agora
        entrega.recebido_por_usuario_id = usuario_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return detalhar(db, negocio_id, loja_id, entrega_id, agora)
