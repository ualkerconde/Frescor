"""
Cadastro mínimo de eventos (datas atípicas) pelo gestor de central
(Fase 3 / F3, decisão D24). Router fino: autentica (obter_gestor_central)
e delega ao eventos_service, que aplica o escopo da central (D8, D27).

- POST /eventos: cria (201) um evento da central do gestor, para todas as
  lojas dela ou para lojas específicas. Validação -> 422 com mensagem.
- GET /eventos?data_inicio&data_fim: lista os eventos que valem para a
  central (datas opcionais: só os que tocam o período).
- DELETE /eventos/{id}: apaga (204). Fora do escopo ou inexistente -> 404;
  evento que vale também para outra central -> 403.

Editar = apagar e criar de novo (API mínima; a tela vem depois).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.evento import EventoCriar, EventoResponse
from app.services.eventos_service import (
    EventoDetalhe,
    EventoForaDoEscopo,
    EventoInvalido,
    EventoNaoEncontrado,
    apagar_evento,
    criar_evento,
    listar_eventos,
)

router = APIRouter()


def _resposta(e: EventoDetalhe) -> EventoResponse:
    return EventoResponse(
        id=e.id,
        nome=e.nome,
        data_inicio=e.data_inicio,
        data_fim=e.data_fim,
        tipo_ajuste=e.tipo_ajuste,
        valor_ajuste=e.valor_ajuste,
        escopo_loja=e.escopo_loja,
        loja_ids=e.loja_ids,
        escopo_produto=e.escopo_produto,
        produto_ids=e.produto_ids,
        pode_apagar=e.pode_apagar,
    )


@router.post("/eventos", response_model=EventoResponse, status_code=status.HTTP_201_CREATED)
def criar(
    corpo: EventoCriar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Cria um evento da central do gestor (todas as lojas ou lojas específicas)."""
    try:
        evento = criar_evento(
            db, gestor, corpo.nome, corpo.data_inicio, corpo.data_fim, corpo.tipo_ajuste,
            corpo.valor_ajuste, corpo.escopo_loja, corpo.loja_ids, corpo.produto_ids,
        )
    except EventoInvalido as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return _resposta(evento)


@router.get("/eventos", response_model=list[EventoResponse])
def listar(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Eventos que valem para a central do gestor."""
    return [_resposta(e) for e in listar_eventos(db, gestor, data_inicio, data_fim)]


@router.delete("/eventos/{evento_id}", status_code=status.HTTP_204_NO_CONTENT)
def apagar(
    evento_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Apaga um evento cujas lojas são todas da central do gestor."""
    try:
        apagar_evento(db, gestor, evento_id)
    except EventoNaoEncontrado as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EventoForaDoEscopo as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
