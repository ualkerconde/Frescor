"""código de produto único dentro do negócio

ID da revisão: 0016
Revisa: 0015
Criada em: 2026-10-13

A importação de vendas e perdas (Fase 2, D7) identifica o produto pelo
`codigo`. Sem unicidade, um código repetido no mesmo negócio tornaria a
linha ambígua. Agora o banco garante: única `(negocio_id, codigo)` em
`produtos`. Produtos sem código (NULL) continuam permitidos em qualquer
quantidade, e o mesmo código pode existir em negócios diferentes.

Antes de criar a constraint, a migração procura códigos repetidos e, se
houver, para com uma mensagem que lista cada um (em vez do erro genérico do
PostgreSQL). Nesse caso, corrija os códigos e rode de novo. Em 2026-10-13 o
banco de desenvolvimento não tinha nenhum repetido; o de produção do app
precisa ser conferido antes do deploy.

Esta migração NÃO é destrutiva -- apenas cria uma constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    repetidos = op.get_bind().execute(sa.text(
        "SELECT negocio_id, codigo, count(*) FROM produtos "
        "WHERE codigo IS NOT NULL GROUP BY negocio_id, codigo HAVING count(*) > 1 "
        "ORDER BY negocio_id, codigo"
    )).all()
    if repetidos:
        lista = "; ".join(f"negocio_id={n} codigo={c!r} ({q} produtos)" for n, c, q in repetidos)
        raise RuntimeError(
            "Não é possível criar a restrição única (negocio_id, codigo) em produtos: "
            f"há códigos repetidos no mesmo negócio. Corrija e rode de novo. {lista}"
        )
    op.create_unique_constraint("uq_produto_negocio_codigo", "produtos", ["negocio_id", "codigo"])


def downgrade() -> None:
    op.drop_constraint("uq_produto_negocio_codigo", "produtos", type_="unique")
