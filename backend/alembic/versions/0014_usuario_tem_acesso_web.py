"""adiciona tem_acesso_web em usuarios

ID da revisão: 0014
Revisa: 0013
Criada em: 2026-10-13

Decisão D1 (docs/STATUS.md): o gestor de central entra no SaaS web por uma
flag própria, separada de `tem_acesso_app` (que continua controlando só o
app mobile). Assim o gestor não precisa ganhar acesso ao app para logar no
SaaS, e um operador de loja não ganha acesso ao SaaS por ter acesso ao app.

- `tem_acesso_web` (Boolean, NOT NULL, server_default false): todos os
  usuários existentes ficam sem acesso ao SaaS, que é o comportamento de
  hoje (o SaaS ainda não existe). O app mobile não lê esta coluna.

Esta migração NÃO é destrutiva -- apenas adiciona uma coluna.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column("tem_acesso_web", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "tem_acesso_web")
