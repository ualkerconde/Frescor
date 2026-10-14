"""
Endpoints de consulta de vendas e perdas diárias (SaaS web, Fase 2 / P6).

Routers finos: autenticam o gestor (obter_gestor_central), validam a loja
contra o escopo (404 idêntico para loja inexistente, de outra central ou de
outro negócio, via app/api/escopo.py) e delegam ao consulta_service.

Parâmetros (query string):
- data_inicio, data_fim: obrigatórias, formato AAAA-MM-DD, inclusive;
  período máximo de 366 dias. Período inválido -> 422 com mensagem.
- loja_id, produto_id: opcionais. Sem loja_id, vêm todas as lojas da
  central do gestor.
- limit (1 a 1000, padrão 100) e offset (padrão 0).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.escopo import loja_no_escopo_ou_404
from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.consulta import (
    ConsultaDiariaResponse,
    ItemDiarioResponse,
    LojaResumo,
    ProdutoResumo,
    TotalPorUnidadeResponse,
)
from app.services.consulta_service import PeriodoInvalido, TipoConsulta, consultar

LIMIT_MAXIMO = 1000

router = APIRouter()


def _consultar(db, gestor, tipo, data_inicio, data_fim, loja_id, produto_id, limit, offset) -> ConsultaDiariaResponse:
    if loja_id is not None:
        loja_no_escopo_ou_404(db, gestor, loja_id)
    try:
        resultado = consultar(db, gestor, tipo, data_inicio, data_fim, loja_id, produto_id, limit, offset)
    except PeriodoInvalido as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return ConsultaDiariaResponse(
        total=resultado.total,
        limit=limit,
        offset=offset,
        totais=[TotalPorUnidadeResponse(unidade=t.unidade, quantidade=t.quantidade) for t in resultado.totais],
        itens=[
            ItemDiarioResponse(
                data=i.data,
                loja=LojaResumo(id=i.loja_id, codigo=i.loja_codigo),
                produto=ProdutoResumo(id=i.produto_id, codigo=i.produto_codigo, nome=i.produto_nome),
                quantidade=i.quantidade,
                unidade=i.unidade,
                origem=i.origem,
            )
            for i in resultado.itens
        ],
    )


@router.get("/vendas", response_model=ConsultaDiariaResponse)
def listar_vendas(
    data_inicio: date = Query(..., description="Primeiro dia do período (AAAA-MM-DD)."),
    data_fim: date = Query(..., description="Último dia do período (AAAA-MM-DD), máximo 366 dias."),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=LIMIT_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Vendas diárias das lojas da central do gestor, no período."""
    return _consultar(db, gestor, TipoConsulta.VENDA, data_inicio, data_fim, loja_id, produto_id, limit, offset)


@router.get("/perdas", response_model=ConsultaDiariaResponse)
def listar_perdas(
    data_inicio: date = Query(..., description="Primeiro dia do período (AAAA-MM-DD)."),
    data_fim: date = Query(..., description="Último dia do período (AAAA-MM-DD), máximo 366 dias."),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=LIMIT_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Perdas diárias das lojas da central do gestor, no período."""
    return _consultar(db, gestor, TipoConsulta.PERDA, data_inicio, data_fim, loja_id, produto_id, limit, offset)
