"""
Tradução do escopo do gestor (app/services/escopo_service.py) para HTTP.

Rotas do SaaS que recebem um `loja_id` usam `loja_no_escopo_ou_404` para
validar o parâmetro. Loja inexistente, de outra central ou de outro negócio
recebem a MESMA resposta (404, mesma mensagem), para não revelar se a loja
existe fora do escopo (decisão D8 em docs/STATUS.md).
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.loja import Loja
from app.services.escopo_service import buscar_loja_no_escopo

MENSAGEM_LOJA_NAO_ENCONTRADA = "Loja não encontrada."


def loja_no_escopo_ou_404(db: Session, gestor: GestorCentralAutenticado, loja_id: int) -> Loja:
    loja = buscar_loja_no_escopo(db, gestor, loja_id)
    if loja is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MENSAGEM_LOJA_NAO_ENCONTRADA)
    return loja
