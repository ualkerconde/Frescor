"""cria tabela centrais_producao

ID da revisão: 0007
Revisa: 0006
Criada em: 2026-08-20

Nova tabela `centrais_producao`: representa a unidade fabril/de
distribuição de uma rede. Cada negócio pode ter uma ou mais centrais.
Toda loja será vinculada a uma central (migração 0008).

Esta migração NÃO é destrutiva — apenas cria uma tabela nova.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "centrais_producao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_centrais_producao_negocio_id", "centrais_producao", ["negocio_id"])


def downgrade() -> None:
    op.drop_index("ix_centrais_producao_negocio_id", table_name="centrais_producao")
    op.drop_table("centrais_producao")
