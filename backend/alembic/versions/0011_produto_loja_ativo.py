"""adiciona ativo em produtos_lojas

ID da revisão: 0011
Revisa: 0010
Criada em: 2026-08-20

Adiciona a coluna `ativo` em `produtos_lojas`. Permite ligar/desligar
um produto para uma loja específica sem remover o vínculo e sem afetar
as demais lojas. Default true para não alterar o comportamento atual.

Nota: a presença/ausência da linha ainda é o mecanismo principal de
habilitação permanente. O campo `ativo` serve para desativação temporária.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "produtos_lojas",
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("produtos_lojas", "ativo")
