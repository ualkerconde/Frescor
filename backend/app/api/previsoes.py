"""
API de previsão do SaaS web (Fase 3 / F8). Routers finos: autenticam o
gestor (obter_gestor_central), validam a loja contra o escopo (404 igual
para loja inexistente, de outra central ou de outro negócio) e delegam aos
serviços. Negócio e central vêm sempre do gestor autenticado.

- POST /previsoes/gerar: calcula e grava os 7 dias seguintes à data de
  referência (padrão: ontem), substituindo a geração anterior (D22).
- GET /previsoes?data=AAAA-MM-DD: previsões gravadas de um dia (padrão:
  amanhã), com componentes, venda da semana passada e totais por unidade.
- GET /previsoes/qualidade?data_inicio&data_fim: WAPE e viés do motor e do
  ingênuo num período de até 28 dias (padrão: as 4 semanas até ontem).
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.escopo import loja_no_escopo_ou_404
from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.previsao import (
    EventoAplicado,
    GeracaoResponse,
    GerarPrevisoesRequest,
    LojaPrevisao,
    PrevisaoItemResponse,
    PrevisoesResponse,
    ProdutoPrevisao,
    QualidadeResponse,
    QualidadeUnidadeResponse,
    TotalPrevistoResponse,
)
from app.services.previsao_consulta_service import (
    PERIODO_MAXIMO_QUALIDADE,
    ConsultaInvalida,
    avaliar_qualidade,
    listar_previsoes,
)
from app.services.previsao_gravacao import VERSAO_METODO, gerar_previsoes

router = APIRouter()


def _4(x: Decimal | None) -> Decimal | None:
    """Métrica com 4 casas (0,1165 = 11,65%); a comparação com o ingênuo usa o valor exato."""
    return None if x is None else x.quantize(Decimal("0.0001"))


def _422(mensagem: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=mensagem)


@router.post("/previsoes/gerar", response_model=GeracaoResponse)
def gerar(
    corpo: Optional[GerarPrevisoesRequest] = None,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Gera (ou atualiza) as previsões dos próximos 7 dias da central do gestor."""
    ontem = date.today() - timedelta(days=1)
    referencia = (corpo.data_referencia if corpo else None) or ontem
    if referencia > ontem:
        raise _422("A data de referência precisa ser no máximo ontem (o dia de hoje ainda não fechou).")
    r = gerar_previsoes(db, gestor.negocio_id, gestor.central_producao_id, referencia, usuario_id=gestor.usuario_id)
    return GeracaoResponse(
        data_referencia=r.data_referencia, data_inicio=r.data_inicio, data_fim=r.data_fim, gravadas=r.gravadas,
        sem_previsao=r.sem_previsao, substituidas=r.substituidas, versao_metodo=VERSAO_METODO,
    )


@router.get("/previsoes", response_model=PrevisoesResponse)
def consultar(
    data: Optional[date] = Query(None, description="Dia previsto (AAAA-MM-DD); padrão: amanhã."),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Previsões gravadas de um dia para as lojas da central do gestor."""
    dia = data or date.today() + timedelta(days=1)
    if loja_id is not None:
        loja_no_escopo_ou_404(db, gestor, loja_id)
    resultado = listar_previsoes(db, gestor, dia, loja_id, produto_id)
    itens = []
    for i in resultado.itens:
        r = i.registro
        itens.append(PrevisaoItemResponse(
            data=r.data,
            loja=LojaPrevisao(id=r.loja_id, codigo=i.loja_codigo, nome=i.loja_nome),
            produto=ProdutoPrevisao(id=r.produto_id, codigo=i.produto_codigo, nome=i.produto_nome),
            unidade=i.unidade,
            previsao=r.previsao,
            previsao_sem_evento=r.previsao_sem_evento,
            previsao_propria=r.previsao_propria,
            venda_semana_passada=i.venda_semana_passada,
            metodo=r.metodo.value,
            estatistica=r.estatistica.value,
            base=r.base,
            semanas_na_base=r.semanas_na_base,
            tendencia=r.tendencia,
            tendencia_bruta=r.tendencia_bruta,
            dias_na_tendencia=r.dias_na_tendencia,
            inicio_historico=r.inicio_historico,
            peso_historico=r.peso_historico,
            pouco_historico=r.peso_historico < 1,
            proxy=r.proxy,
            origem_proxy=r.origem_proxy.value if r.origem_proxy else None,
            eventos=[EventoAplicado(**e) for e in r.eventos],
            data_referencia=r.data_referencia,
            gerado_em=r.gerado_em,
            versao_metodo=r.versao_metodo,
        ))
    return PrevisoesResponse(
        data=dia,
        itens=itens,
        totais=[TotalPrevistoResponse(unidade=t.unidade, previsto=t.previsto,
                                      vendido_semana_passada=t.vendido_semana_passada) for t in resultado.totais],
    )


@router.get("/previsoes/qualidade", response_model=QualidadeResponse)
def qualidade(
    data_inicio: Optional[date] = Query(None, description=f"Padrão: {PERIODO_MAXIMO_QUALIDADE} dias até ontem."),
    data_fim: Optional[date] = Query(None, description="Padrão: ontem."),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Teste no passado: quanto o motor erraria em cada dia do período, contra o ingênuo."""
    hoje = date.today()
    fim = data_fim or hoje - timedelta(days=1)
    inicio = data_inicio or fim - timedelta(days=PERIODO_MAXIMO_QUALIDADE - 1)
    if loja_id is not None:
        loja_no_escopo_ou_404(db, gestor, loja_id)
    try:
        r = avaliar_qualidade(db, gestor, inicio, fim, loja_id, produto_id, hoje)
    except ConsultaInvalida as e:
        raise _422(str(e))
    return QualidadeResponse(
        data_inicio=r.data_inicio,
        data_fim=r.data_fim,
        por_unidade=[
            QualidadeUnidadeResponse(
                unidade=u.unidade, pares=u.motor.n, wape=_4(u.motor.wape), vies=_4(u.motor.vies),
                ingenuo_wape=_4(u.ingenuo.wape), ingenuo_vies=_4(u.ingenuo.vies), vence_ingenuo=u.vence_ingenuo,
            )
            for u in r.por_unidade
        ],
    )
