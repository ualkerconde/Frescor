"""
Dados de apoio às telas do SaaS web (frontend, passo W1): quem é o gestor
logado e o catálogo de produtos do negócio, para cabeçalho e filtros.

As lojas do gestor vêm do escopo_service (D8: só a central dele). Aqui
ficam o "quem sou eu" e a busca de produtos, que é do NEGÓCIO inteiro (o
catálogo é do negócio, não da central -- doc de referência §3.1).

Busca de produtos: por código ou nome, sem diferenciar maiúsculas NEM
acentos ("pao" acha "Pão"; extensão `unaccent`, migration 0017); `%` e `_`
digitados pelo usuário são texto, não curinga.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.central_producao import CentralProducao
from app.models.negocio import Negocio
from app.models.produto import Produto
from app.models.usuario import Usuario


@dataclass
class DadosGestor:
    usuario_id: int
    nome: str
    email: str
    central_id: int
    central_nome: str
    negocio_id: int
    negocio_nome: str


def dados_do_gestor(db: Session, gestor: GestorCentralAutenticado) -> DadosGestor:
    """Nome do gestor, da central e do negócio, a partir da identidade autenticada."""
    usuario = db.get(Usuario, gestor.usuario_id)
    central = db.get(CentralProducao, gestor.central_producao_id)
    negocio = db.get(Negocio, gestor.negocio_id)
    return DadosGestor(
        usuario_id=usuario.id,
        nome=usuario.nome,
        email=usuario.email,
        central_id=central.id,
        central_nome=central.nome,
        negocio_id=negocio.id,
        negocio_nome=negocio.nome,
    )


def listar_produtos(
    db: Session,
    gestor: GestorCentralAutenticado,
    busca: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Produto]]:
    """(total, página) dos produtos do negócio do gestor, ordenados por código e nome."""
    consulta = db.query(Produto).filter(Produto.negocio_id == gestor.negocio_id)
    termo = (busca or "").strip()
    if termo:
        # Escapa os curingas do LIKE para valerem como texto; o unaccent
        # não altera "\", "%" nem "_", então o escape sobrevive a ele.
        escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        padrao = func.lower(func.unaccent(f"%{escapado}%"))

        def normalizado(coluna):
            return func.lower(func.unaccent(coluna))

        consulta = consulta.filter(or_(
            normalizado(Produto.codigo).like(padrao, escape="\\"),
            normalizado(Produto.nome).like(padrao, escape="\\"),
        ))
    total = consulta.count()
    itens = (
        consulta.order_by(Produto.codigo.asc().nulls_last(), Produto.nome, Produto.id)
        .limit(limit)
        .offset(offset)
        .all()
    )
    return total, itens
