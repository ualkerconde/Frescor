"""
Endpoint de verificação de saúde (health check).

Usado para confirmar rapidamente que:
1. A API está rodando.
2. A conexão com o banco de dados está funcionando.

Útil tanto durante o desenvolvimento quanto, futuramente, para serviços de
monitoramento em produção.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    # Executa a consulta mais simples possível só para confirmar que o
    # banco responde.
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "conectado"}
