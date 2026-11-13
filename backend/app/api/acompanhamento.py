"""
Acompanhamento (dashboard, D115/D116). Router fino sobre `acompanhamento_service`.

GET /web/acompanhamento?data_inicio=&data_fim=&loja_id=&produto_id=
- Padrão: os 7 dias até ontem (a venda de hoje ainda não chegou). Até 28 dias.
- Só lojas da central do gestor; loja de fora -> 404 (igual às outras rotas).
- Números como texto decimal, como no resto da API.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.escopo import loja_no_escopo_ou_404
from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.services import acompanhamento_service as svc
from app.services.escopo_service import ids_lojas_do_gestor
from app.services.perda_lancamento_service import hoje_local

router = APIRouter()


class Valores(BaseModel):
    previsto: Decimal | None
    sugerido: Decimal | None
    final: Decimal | None
    produzido: Decimal | None
    enviado: Decimal | None
    vendido: Decimal | None
    perda: Decimal | None
    # D111: esperado − contado (+ = sumiu sem registro). Só das células com balanço.
    sem_registro: Decimal | None


class ErroPrevisao(BaseModel):
    wape: Decimal | None
    vies: Decimal | None
    celulas: int


class DiaAcompanhamento(Valores):
    data: date


class UnidadeAcompanhamento(BaseModel):
    unidade: str
    totais: Valores
    erro: ErroPrevisao
    dias: list[DiaAcompanhamento]
    balancos: int  # células loja × produto × dia com balanço da contagem (D111)
    rupturas: int  # dessas, quantas fecharam com contagem zero e venda no dia


class ProdutoAcompanhamento(BaseModel):
    produto: dict
    unidade: str
    totais: Valores
    erro: ErroPrevisao
    sobra: Decimal | None
    balancos: int
    rupturas: int


class AcompanhamentoResponse(BaseModel):
    data_inicio: date
    data_fim: date
    produzido_disponivel: bool
    unidades: list[UnidadeAcompanhamento]
    produtos: list[ProdutoAcompanhamento]


def _erro(e: svc.Erro) -> ErroPrevisao:
    q = lambda v: None if v is None else v.quantize(Decimal("0.0001"))  # noqa: E731
    return ErroPrevisao(wape=q(e.wape), vies=q(e.vies), celulas=e.celulas)


@router.get("/web/acompanhamento", response_model=AcompanhamentoResponse, tags=["Acompanhamento (SaaS web)"])
def acompanhamento(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    fim = data_fim or hoje_local() - timedelta(days=1)
    inicio = data_inicio or fim - timedelta(days=svc.PERIODO_PADRAO_DIAS - 1)
    if loja_id is not None:
        lojas = [loja_no_escopo_ou_404(db, gestor, loja_id).id]
    else:
        lojas = ids_lojas_do_gestor(db, gestor)
    try:
        r = svc.acompanhamento(db, gestor.negocio_id, gestor.central_producao_id, lojas, inicio, fim, produto_id,
                               por_loja=loja_id is not None)
    except svc.PeriodoInvalido as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
    return AcompanhamentoResponse(
        data_inicio=r.data_inicio,
        data_fim=r.data_fim,
        produzido_disponivel=r.produzido_disponivel,
        unidades=[
            UnidadeAcompanhamento(
                unidade=s.unidade, totais=Valores(**s.totais.valores), erro=_erro(s.erro),
                dias=[DiaAcompanhamento(data=d, **linha.valores) for d, linha in sorted(s.dias.items())],
                balancos=s.balancos, rupturas=s.rupturas,
            )
            for s in r.unidades
        ],
        produtos=[
            ProdutoAcompanhamento(
                produto={"id": p.produto_id, "codigo": p.produto_codigo, "nome": p.produto_nome}, unidade=p.unidade,
                totais=Valores(**p.totais.valores), erro=_erro(p.erro), sobra=p.sobra,
                balancos=p.balancos, rupturas=p.rupturas,
            )
            for p in r.produtos
        ],
    )
