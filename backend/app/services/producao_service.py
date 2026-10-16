"""
Ordem de produção do dia (Fase 4 / N6): gerar, editar, aprovar e apagar,
e o provedor de estoque em trânsito para a necessidade (D43, D52).

Fluxo (D38): o gestor gera a ordem de uma data de produção -> ela nasce em
`rascunho`, com a necessidade de cada loja + produto como quantidade
sugerida e também como final -> o gestor ajusta a final loja por loja ->
aprova. A ordem aprovada fica travada e passa a ser trânsito para as
ordens seguintes até a loja confirmar o recebimento (Fase 5).

Regras:
- Gerar de novo SUBSTITUI o rascunho daquela central e data (apaga a ordem;
  itens e linhas saem em cascata) e perde os ajustes do gestor. Ordem
  APROVADA não é regerada nem apagada: ela é o trânsito das próximas
  ordens; apagá-la faria a central produzir de novo o que já mandou.
- Tudo ou nada: a ordem só é gravada inteira; qualquer erro desfaz tudo.
  Duas gerações/aprovações simultâneas da mesma central esperam uma pela
  outra (trava `pg_advisory_xact_lock` da central).
- Previsão desatualizada (D41): antes de calcular, se a previsão gravada é
  de referência anterior a ontem, ela é gerada de novo (referência ontem).
- Aprovar exige quantidade final em todas as linhas (produto sem previsão
  ou sem calendário nasce sem quantidade: o gestor informa) e confere que
  cada loja ainda é ativa na central da ordem (D57).
- Edição: final >= 0; UN em inteiro (como na importação, D13); KG com até
  3 casas. Grava quem, quando e o motivo (só a última edição, D56).
- `negocio_id`, `central_producao_id` e `usuario_id` vêm do gestor
  autenticado (a rota passa os dados de `obter_gestor_central`); ordem ou
  linha de outra central ou negócio responde como inexistente.

Trânsito (D43, D52): `provedor_transito_ordens` devolve, por loja +
produto, as linhas de ordens APROVADAS ainda sem recebimento confirmado
(`recebido_em` NULL) com entrega a partir de D. Entrega antes de D conta
como já recebida no fim do dia de entrega (está na contagem de D−1); a
linha da necessidade ganha o aviso "recebimento não confirmado" quando há
entrega assim nos 7 dias antes de D.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.loja import Loja
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao, TipoOrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.produto import TipoAbastecimento, UnidadeMedida
from app.services.necessidade_calculo import VERSAO_METODO_NECESSIDADE, LoteTransito
from app.services.necessidade_service import NecessidadesCentral, Par, calcular_necessidades
from app.services.previsao_gravacao import HORIZONTE_DIAS, gerar_previsoes

AVISO_RECEBIMENTO_NAO_CONFIRMADO = "recebimento_nao_confirmado"  # D43
DIAS_AVISO_RECEBIMENTO = 7
CASAS_KG = Decimal("0.001")
# Trava por central (primeiro inteiro separa das travas da previsão, 3001).
_TRAVA_ORDEM = 3002

AtualizarPrevisao = Callable[..., object]


class OrdemNaoEncontrada(LookupError):
    """Ordem ou linha inexistente, ou de outra central/negócio."""


class OrdemAprovada(ValueError):
    """Ordem aprovada não pode ser editada, regerada nem apagada."""


class OrdemInvalida(ValueError):
    """Pedido que fere uma regra da ordem (mensagem para o gestor)."""


@dataclass(frozen=True)
class ResultadoGeracaoOrdem:
    ordem_id: int
    data_producao: date
    data_entrega: date
    itens: int
    linhas: int
    sem_quantidade: int
    substituiu_rascunho: bool
    previsao_atualizada: bool


def _travar(db: Session, central_producao_id: int) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": _TRAVA_ORDEM, "b": central_producao_id})


def _json(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return [_json(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _json(v) for k, v in valor.items()}
    return valor


def _linhas_aprovadas_pendentes(db: Session, negocio_id: int, lojas: Sequence[int]):
    """Linhas de ordens aprovadas, sem recebimento confirmado, das lojas (qualquer central)."""
    return (
        db.query(OrdemProducaoLinha.loja_id, OrdemProducaoItem.produto_id, OrdemProducao.data_entrega,
                 OrdemProducaoLinha.quantidade_final)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(OrdemProducao, OrdemProducao.id == OrdemProducaoItem.ordem_id)
        .filter(
            OrdemProducao.negocio_id == negocio_id,
            OrdemProducaoLinha.negocio_id == negocio_id,
            OrdemProducao.status == StatusOrdemProducao.APROVADA,
            OrdemProducaoLinha.loja_id.in_(list(lojas)),
            OrdemProducaoLinha.recebido_em.is_(None),
        )
    )


def provedor_transito_ordens(
    db: Session, negocio_id: int, lojas: Sequence[int], data_producao: date
) -> dict[Par, list[LoteTransito]]:
    """D43/D52: trânsito por loja + produto (entrega a partir de D)."""
    transito: dict[Par, list[LoteTransito]] = defaultdict(list)
    for loja_id, produto_id, entrega, quantidade in _linhas_aprovadas_pendentes(db, negocio_id, lojas).filter(
        OrdemProducao.data_entrega >= data_producao
    ):
        if quantidade is not None and quantidade > 0:
            transito[(loja_id, produto_id)].append(LoteTransito(entrega, Decimal(quantidade)))
    return dict(transito)


def _recebimentos_presumidos(db: Session, negocio_id: int, lojas: Sequence[int], data_producao: date) -> set[Par]:
    inicio = data_producao - timedelta(days=DIAS_AVISO_RECEBIMENTO)
    return {
        (loja_id, produto_id)
        for loja_id, produto_id, _, _ in _linhas_aprovadas_pendentes(db, negocio_id, lojas).filter(
            OrdemProducao.data_entrega >= inicio, OrdemProducao.data_entrega < data_producao
        )
    }


def _ordem_programada(db: Session, negocio_id: int, central_producao_id: int, data_producao: date):
    return (
        db.query(OrdemProducao)
        .filter(
            OrdemProducao.negocio_id == negocio_id,
            OrdemProducao.central_producao_id == central_producao_id,
            OrdemProducao.data_producao == data_producao,
            OrdemProducao.tipo == TipoOrdemProducao.PROGRAMADA,
        )
        .one_or_none()
    )


def gerar_ordem(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    data_producao: date,
    usuario_id: int | None,
    hoje: date,
    atualizar_previsao: AtualizarPrevisao | None = gerar_previsoes,
) -> ResultadoGeracaoOrdem:
    """Gera (ou regera, se rascunho) a ordem programada da central para `data_producao`."""
    if data_producao < hoje:
        raise OrdemInvalida("Não é possível gerar ordem para uma data que já passou.")
    if data_producao >= hoje + timedelta(days=HORIZONTE_DIAS):
        raise OrdemInvalida(f"A ordem pode ser gerada para até {HORIZONTE_DIAS - 1} dias à frente.")

    # Recusa cedo (antes de mexer na previsão) se a ordem do dia já foi aprovada.
    existente = _ordem_programada(db, negocio_id, central_producao_id, data_producao)
    if existente is not None and existente.status == StatusOrdemProducao.APROVADA:
        raise OrdemAprovada("A ordem deste dia já foi aprovada e não pode ser gerada de novo.")

    necessidades: NecessidadesCentral = calcular_necessidades(
        db, negocio_id, central_producao_id, data_producao, hoje, provedor_transito=provedor_transito_ordens
    )
    previsao_atualizada = False
    if necessidades.previsao_desatualizada and atualizar_previsao is not None and necessidades.itens:
        # D41. gerar_previsoes grava e confirma numa transação própria.
        atualizar_previsao(db, negocio_id, central_producao_id, hoje - timedelta(days=1), usuario_id=usuario_id)
        previsao_atualizada = True
        necessidades = calcular_necessidades(
            db, negocio_id, central_producao_id, data_producao, hoje, provedor_transito=provedor_transito_ordens
        )

    try:
        _travar(db, central_producao_id)
        existente = _ordem_programada(db, negocio_id, central_producao_id, data_producao)
        substituiu = False
        if existente is not None:
            if existente.status == StatusOrdemProducao.APROVADA:
                raise OrdemAprovada("A ordem deste dia já foi aprovada e não pode ser gerada de novo.")
            db.delete(existente)
            db.flush()
            substituiu = True

        ordem = OrdemProducao(
            negocio_id=negocio_id,
            central_producao_id=central_producao_id,
            data_producao=data_producao,
            data_entrega=data_producao + timedelta(days=necessidades.prazo_entrega_dias),
            tipo=TipoOrdemProducao.PROGRAMADA,
            status=StatusOrdemProducao.RASCUNHO,
            versao_metodo=VERSAO_METODO_NECESSIDADE,
            referencia_previsao=necessidades.referencia_previsao,
            gerado_por_usuario_id=usuario_id,
        )
        db.add(ordem)
        db.flush()

        lojas = sorted({i.loja_id for i in necessidades.itens})
        presumidos = _recebimentos_presumidos(db, negocio_id, lojas, data_producao) if lojas else set()
        itens: dict[int, OrdemProducaoItem] = {}
        linhas = sem_quantidade = 0
        for x in necessidades.itens:
            item = itens.get(x.produto_id)
            if item is None:
                item = OrdemProducaoItem(
                    negocio_id=negocio_id, ordem_id=ordem.id, produto_id=x.produto_id,
                    tipo_abastecimento=TipoAbastecimento(x.tipo_abastecimento), unidade=UnidadeMedida(x.unidade),
                )
                db.add(item)
                db.flush()
                itens[x.produto_id] = item
            avisos = list(x.resultado.avisos)
            if (x.loja_id, x.produto_id) in presumidos:
                avisos.append(AVISO_RECEBIMENTO_NAO_CONFIRMADO)
            componentes = _json(asdict(x.resultado))
            componentes.update(pouco_historico=x.pouco_historico, taxa_perda=_json(x.taxa_perda))
            db.add(OrdemProducaoLinha(
                negocio_id=negocio_id, item_id=item.id, loja_id=x.loja_id,
                quantidade_sugerida=x.resultado.necessidade, quantidade_final=x.resultado.necessidade,
                componentes=componentes, avisos=avisos,
            ))
            linhas += 1
            sem_quantidade += x.resultado.necessidade is None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ResultadoGeracaoOrdem(
        ordem_id=ordem.id, data_producao=data_producao, data_entrega=ordem.data_entrega, itens=len(itens),
        linhas=linhas, sem_quantidade=sem_quantidade, substituiu_rascunho=substituiu,
        previsao_atualizada=previsao_atualizada,
    )


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
        raise OrdemNaoEncontrada("Ordem de produção não encontrada.")
    return ordem


def editar_linha(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    linha_id: int,
    quantidade_final: Decimal,
    usuario_id: int,
    motivo: str | None = None,
    agora: datetime | None = None,
    ordem_id: int | None = None,
) -> OrdemProducaoLinha:
    """Muda a quantidade final de uma loja (só em rascunho). Com `ordem_id`, a linha tem de ser dessa ordem."""
    consulta = (
        db.query(OrdemProducaoLinha, OrdemProducaoItem, OrdemProducao)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(OrdemProducao, OrdemProducao.id == OrdemProducaoItem.ordem_id)
        .filter(
            OrdemProducaoLinha.id == linha_id,
            OrdemProducaoLinha.negocio_id == negocio_id,
            OrdemProducao.negocio_id == negocio_id,
            OrdemProducao.central_producao_id == central_producao_id,
        )
    )
    if ordem_id is not None:
        consulta = consulta.filter(OrdemProducao.id == ordem_id)
    encontrado = consulta.one_or_none()
    if encontrado is None:
        raise OrdemNaoEncontrada("Linha da ordem não encontrada.")
    linha, item, ordem = encontrado
    if ordem.status != StatusOrdemProducao.RASCUNHO:
        raise OrdemAprovada("A ordem já foi aprovada e não pode ser alterada.")
    quantidade = Decimal(quantidade_final)
    if quantidade < 0:
        raise OrdemInvalida("A quantidade não pode ser negativa.")
    if item.unidade == UnidadeMedida.UN and quantidade != quantidade.to_integral_value():
        raise OrdemInvalida("Produto vendido por unidade: informe um número inteiro.")
    if quantidade != quantidade.quantize(CASAS_KG):
        raise OrdemInvalida("Informe no máximo 3 casas decimais.")
    if motivo is not None and len(motivo) > 255:
        raise OrdemInvalida("O motivo pode ter no máximo 255 caracteres.")
    linha.quantidade_final = quantidade
    linha.editado_em = agora or datetime.utcnow()
    linha.editado_por_usuario_id = usuario_id
    linha.motivo_edicao = motivo or None
    db.commit()
    return linha


def aprovar_ordem(
    db: Session, negocio_id: int, central_producao_id: int, ordem_id: int, usuario_id: int,
    agora: datetime | None = None,
) -> OrdemProducao:
    """Rascunho -> aprovada. Exige final em todas as linhas e lojas ainda ativas na central (D57)."""
    try:
        _travar(db, central_producao_id)
        ordem = _buscar_ordem(db, negocio_id, central_producao_id, ordem_id)
        if ordem.status != StatusOrdemProducao.RASCUNHO:
            raise OrdemAprovada("A ordem já foi aprovada.")
        linhas = (
            db.query(OrdemProducaoLinha)
            .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
            .filter(OrdemProducaoItem.ordem_id == ordem.id, OrdemProducaoLinha.negocio_id == negocio_id)
            .all()
        )
        sem_quantidade = [linha.id for linha in linhas if linha.quantidade_final is None]
        if sem_quantidade:
            raise OrdemInvalida(
                f"Informe a quantidade de {len(sem_quantidade)} linha(s) antes de aprovar "
                "(produtos sem previsão ou sem calendário)."
            )
        lojas_da_central = {
            loja_id for (loja_id,) in db.query(Loja.id).filter(
                Loja.negocio_id == negocio_id, Loja.central_producao_id == central_producao_id, Loja.ativo.is_(True)
            )
        }
        fora = sorted({linha.loja_id for linha in linhas} - lojas_da_central)
        if fora:
            nomes = [nome for (nome,) in db.query(Loja.nome).filter(Loja.negocio_id == negocio_id, Loja.id.in_(fora))]
            raise OrdemInvalida(
                f"Loja(s) que não são mais ativas nesta central: {', '.join(sorted(nomes))}. Gere a ordem de novo."
            )
        ordem.status = StatusOrdemProducao.APROVADA
        ordem.aprovado_em = agora or datetime.utcnow()
        ordem.aprovado_por_usuario_id = usuario_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ordem


def apagar_ordem(db: Session, negocio_id: int, central_producao_id: int, ordem_id: int) -> None:
    """Apaga um rascunho. Ordem aprovada não pode ser apagada (é trânsito, D43)."""
    try:
        _travar(db, central_producao_id)
        ordem = _buscar_ordem(db, negocio_id, central_producao_id, ordem_id)
        if ordem.status != StatusOrdemProducao.RASCUNHO:
            raise OrdemAprovada("A ordem já foi aprovada e não pode ser apagada.")
        db.delete(ordem)
        db.commit()
    except Exception:
        db.rollback()
        raise


def totais_por_produto(db: Session, negocio_id: int, ordem_id: int) -> dict[int, Decimal]:
    """D54: quantidade do item = soma das finais das linhas (sem final conta 0)."""
    totais: dict[int, Decimal] = defaultdict(Decimal)
    for produto_id, final in (
        db.query(OrdemProducaoItem.produto_id, OrdemProducaoLinha.quantidade_final)
        .join(OrdemProducaoLinha, OrdemProducaoLinha.item_id == OrdemProducaoItem.id)
        .filter(OrdemProducaoItem.ordem_id == ordem_id, OrdemProducaoItem.negocio_id == negocio_id)
    ):
        totais[produto_id] += Decimal(final) if final is not None else Decimal(0)
    return dict(totais)
