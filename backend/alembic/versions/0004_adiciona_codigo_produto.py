"""adiciona campo codigo em produtos

ID da revisão: 0004
Revisa: 0003
Criada em: 2026-07-02

Adiciona o campo `codigo` (código interno do negócio) na tabela `produtos`.
Campo opcional, independente de `codigo_barras`, para negócios que usam
sistemas de codificação próprios.

Esta migração NÃO é destrutiva — apenas adiciona uma coluna nova,
sem afetar dados existentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "produtos",
        sa.Column("codigo", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_produtos_codigo", "produtos", ["codigo"])


def downgrade() -> None:
    op.drop_index("ix_produtos_codigo", table_name="produtos")
    op.drop_column("produtos", "codigo")
