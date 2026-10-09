"""cria tabela calendario_producao

ID da revisao: 0012
Revisa: 0011
Criada em: 2026-08-20

Nova tabela `calendario_producao`: define em quais dias da semana cada
produto deve ser produzido pela central. Unicidade de (produto_id, dia_semana)
garantida por constraint de banco.

Nota: tipo enum criado via SQL cru; PgEnum(create_type=False) referencia
o tipo ja existente sem recria-lo.
Nome 'diasemana' = DiaSemana.__name__.lower() -- padrao SQLAlchemy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "CREATE TYPE diasemana AS ENUM "
        "('segunda','terca','quarta','quinta','sexta','sabado','domingo')"
    ))
    op.create_table(
        "calendario_producao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("dia_semana", PgEnum(name="diasemana", create_type=False), nullable=False),
        sa.UniqueConstraint("produto_id", "dia_semana", name="uq_calendario_produto_dia"),
    )
    op.create_index("ix_calendario_producao_produto_id", "calendario_producao", ["produto_id"])


def downgrade() -> None:
    op.drop_index("ix_calendario_producao_produto_id", table_name="calendario_producao")
    op.drop_table("calendario_producao")
    op.execute(sa.text("DROP TYPE IF EXISTS diasemana"))
