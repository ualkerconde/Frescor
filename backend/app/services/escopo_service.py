"""
Escopo de dados do gestor de central no SaaS web (decisão D8 em
docs/STATUS.md): o gestor só enxerga as lojas da PRÓPRIA central de
produção, não todas as lojas do negócio.

Por que um serviço próprio: toda rota do SaaS que recebe um `loja_id`
(como filtro de consulta ou destino de importação) precisa conferir se a
loja está no escopo do gestor. Concentrar a regra aqui evita que cada rota
reimplemente o filtro e esqueça uma das condições.

Regras:
- O escopo é calculado a partir de `GestorCentralAutenticado`, que vem do
  usuário autenticado (negocio_id e central_producao_id lidos do banco),
  nunca de parâmetro da requisição.
- Filtra por `negocio_id` E por `central_producao_id`: a central já
  pertence a um negócio, mas o filtro duplo segue a regra de ouro de toda
  query filtrar por negócio.
- Lojas inativas da central ESTÃO no escopo (ex.: consultar o histórico de
  uma loja desativada). Se alguma operação não deve valer para loja
  inativa (ex.: importar), a regra fica na própria operação. Ponto em
  aberto registrado no STATUS.md.
- Este serviço não conhece HTTP: devolve a loja ou None. A conversão para
  404 fica em app/api/escopo.py.
"""

from typing import Optional

from sqlalchemy.orm import Query, Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.loja import Loja


def consulta_lojas_do_gestor(db: Session, gestor: GestorCentralAutenticado) -> Query:
    """Query das lojas no escopo do gestor (para compor com outros filtros)."""
    return db.query(Loja).filter(
        Loja.negocio_id == gestor.negocio_id,
        Loja.central_producao_id == gestor.central_producao_id,
    )


def ids_lojas_do_gestor(db: Session, gestor: GestorCentralAutenticado) -> list[int]:
    """IDs das lojas no escopo do gestor, em ordem crescente."""
    return [lj.id for lj in consulta_lojas_do_gestor(db, gestor).order_by(Loja.id)]


def buscar_loja_no_escopo(db: Session, gestor: GestorCentralAutenticado, loja_id: int) -> Optional[Loja]:
    """
    Devolve a loja se ela estiver no escopo do gestor; None se não existir,
    for de outra central ou de outro negócio. Os três casos são
    indistinguíveis de propósito, para não revelar a existência de lojas
    fora do escopo.
    """
    return consulta_lojas_do_gestor(db, gestor).filter(Loja.id == loja_id).first()
