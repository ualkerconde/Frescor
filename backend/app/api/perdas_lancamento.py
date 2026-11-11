"""
Lançamento de perda (D110). Routers finos sobre `perda_lancamento_service`.

App mobile (operador; a loja vem do token, regra de ouro 1):
- GET    /perdas/lancamentos          lançamentos da loja de hoje e de ontem
- POST   /perdas/lancamentos          lança (hoje ou ontem)
- PUT    /perdas/lancamentos/{id}     corrige (até o fim de D+1)
- DELETE /perdas/lancamentos/{id}     apaga (até o fim de D+1)

SaaS web (gestor; só lojas da própria central, 404 igual para o resto):
- GET    /web/perdas/lancamentos?data_inicio=&data_fim=&loja_id=&produto_id=  (até 92 dias)
- POST   /web/perdas/lancamentos      lança para uma loja da central, em qualquer dia passado
- PUT    /web/perdas/lancamentos/{id}
- DELETE /web/perdas/lancamentos/{id}

Rotas novas: não mudam `/produtos`, `/estoque`, `/zeragem` nem `/auth`.
Erros: 404 (não encontrado ou fora do escopo), 409 (prazo da loja), 422 (dado inválido).
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.escopo import loja_no_escopo_ou_404
from app.core.dependencies import (
    GestorCentralAutenticado,
    UsuarioAutenticado,
    obter_gestor_central,
    obter_usuario_autenticado,
)
from app.db.session import get_db
from app.schemas.perda import AlterarPerda, LancamentoPerdaResponse, LancarPerdaApp, LancarPerdaWeb
from app.services import perda_lancamento_service as svc
from app.services.escopo_service import ids_lojas_do_gestor

router = APIRouter()
PERIODO_MAXIMO_DIAS = 92


class _Erros:
    def __enter__(self):
        return self

    def __exit__(self, tipo, erro, _tb):
        if erro is None:
            return False
        if isinstance(erro, svc.LancamentoNaoEncontrado):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
        if isinstance(erro, svc.LancamentoBloqueado):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
        if isinstance(erro, svc.LancamentoInvalido):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
        return False


def _resposta(l: svc.Lancamento) -> LancamentoPerdaResponse:
    return LancamentoPerdaResponse(
        id=l.id, data=l.data, loja={"id": l.loja_id, "codigo": l.loja_codigo, "nome": l.loja_nome},
        produto={"id": l.produto_id, "codigo": l.produto_codigo, "nome": l.produto_nome}, unidade=l.unidade,
        quantidade=l.quantidade, motivo=l.motivo, observacao=l.observacao, lancado_por=l.lancado_por,
        lancado_em=l.lancado_em, alterado_por=l.alterado_por, alterado_em=l.alterado_em,
        loja_pode_alterar=l.loja_pode_alterar,
    )


def _um(db, negocio_id, lojas, lancamento_id) -> LancamentoPerdaResponse:
    for l in svc.listar(db, negocio_id, lojas, date.min, date.max):
        if l.id == lancamento_id:
            return _resposta(l)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lançamento não encontrado.")


# ------------------------------------------------------------------ app

def _loja(atual: UsuarioAutenticado) -> int:
    if atual.loja_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seu usuário não está ligado a uma loja.")
    return atual.loja_id


@router.get("/perdas/lancamentos", response_model=list[LancamentoPerdaResponse], tags=["Perda (app mobile)"])
def listar_app(db: Session = Depends(get_db), atual: UsuarioAutenticado = Depends(obter_usuario_autenticado)):
    """Lançamentos de perda da loja de hoje e de ontem, do mais novo."""
    hoje = svc.hoje_local()
    return [_resposta(l) for l in svc.listar(db, atual.negocio_id, [_loja(atual)], hoje - timedelta(days=1), hoje)]


@router.post("/perdas/lancamentos", response_model=LancamentoPerdaResponse, status_code=201,
             tags=["Perda (app mobile)"])
def lancar_app(corpo: LancarPerdaApp, db: Session = Depends(get_db),
               atual: UsuarioAutenticado = Depends(obter_usuario_autenticado)):
    loja = _loja(atual)
    with _Erros():
        novo = svc.lancar(db, atual.negocio_id, loja, atual.usuario_id, corpo.produto_id, corpo.quantidade,
                          corpo.motivo, corpo.observacao, corpo.data, pela_loja=True)
    return _um(db, atual.negocio_id, [loja], novo)


@router.put("/perdas/lancamentos/{lancamento_id}", response_model=LancamentoPerdaResponse,
            tags=["Perda (app mobile)"])
def alterar_app(lancamento_id: int, corpo: AlterarPerda, db: Session = Depends(get_db),
                atual: UsuarioAutenticado = Depends(obter_usuario_autenticado)):
    loja = _loja(atual)
    with _Erros():
        svc.alterar(db, atual.negocio_id, [loja], atual.usuario_id, lancamento_id, corpo.quantidade, corpo.motivo,
                    corpo.observacao, pela_loja=True)
    return _um(db, atual.negocio_id, [loja], lancamento_id)


@router.delete("/perdas/lancamentos/{lancamento_id}", status_code=204, tags=["Perda (app mobile)"])
def apagar_app(lancamento_id: int, db: Session = Depends(get_db),
               atual: UsuarioAutenticado = Depends(obter_usuario_autenticado)):
    with _Erros():
        svc.apagar(db, atual.negocio_id, [_loja(atual)], lancamento_id, pela_loja=True)
    return Response(status_code=204)


# ------------------------------------------------------------------ SaaS

@router.get("/web/perdas/lancamentos", response_model=list[LancamentoPerdaResponse], tags=["Perda (SaaS web)"])
def listar_web(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    loja_id: Optional[int] = Query(None),
    produto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    if data_fim < data_inicio:
        raise HTTPException(status_code=422, detail="A data final não pode ser antes da inicial.")
    if (data_fim - data_inicio).days + 1 > PERIODO_MAXIMO_DIAS:
        raise HTTPException(status_code=422, detail=f"O período pode ter até {PERIODO_MAXIMO_DIAS} dias.")
    if loja_id is not None:
        lojas = [loja_no_escopo_ou_404(db, gestor, loja_id).id]
    else:
        lojas = ids_lojas_do_gestor(db, gestor)
    return [_resposta(l) for l in svc.listar(db, gestor.negocio_id, lojas, data_inicio, data_fim, produto_id)]


@router.post("/web/perdas/lancamentos", response_model=LancamentoPerdaResponse, status_code=201,
             tags=["Perda (SaaS web)"])
def lancar_web(corpo: LancarPerdaWeb, db: Session = Depends(get_db),
               gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    loja = loja_no_escopo_ou_404(db, gestor, corpo.loja_id)
    with _Erros():
        novo = svc.lancar(db, gestor.negocio_id, loja.id, gestor.usuario_id, corpo.produto_id, corpo.quantidade,
                          corpo.motivo, corpo.observacao, corpo.data, pela_loja=False)
    return _um(db, gestor.negocio_id, [loja.id], novo)


@router.put("/web/perdas/lancamentos/{lancamento_id}", response_model=LancamentoPerdaResponse,
            tags=["Perda (SaaS web)"])
def alterar_web(lancamento_id: int, corpo: AlterarPerda, db: Session = Depends(get_db),
                gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    lojas = ids_lojas_do_gestor(db, gestor)
    with _Erros():
        svc.alterar(db, gestor.negocio_id, lojas, gestor.usuario_id, lancamento_id, corpo.quantidade, corpo.motivo,
                    corpo.observacao, pela_loja=False)
    return _um(db, gestor.negocio_id, lojas, lancamento_id)


@router.delete("/web/perdas/lancamentos/{lancamento_id}", status_code=204, tags=["Perda (SaaS web)"])
def apagar_web(lancamento_id: int, db: Session = Depends(get_db),
               gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    with _Erros():
        svc.apagar(db, gestor.negocio_id, ids_lojas_do_gestor(db, gestor), lancamento_id, pela_loja=False)
    return Response(status_code=204)
