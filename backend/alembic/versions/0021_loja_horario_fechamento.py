"""horário de fechamento da loja (D44)

ID da revisão: 0021
Revisa: 0020
Criada em: 2026-10-15

Fase 4 / N3. A contagem de estoque só vale para a necessidade se foi feita
desde o fechamento da loja em D−1 (menos 2 h de folga), na hora local da
loja (D33, D44). Até aqui o banco não sabia quando a loja fecha.

`lojas.horario_fechamento` (Time, NOT NULL, padrão 21:00, hora local): as
lojas existentes ficam com 21:00. Coluna com `server_default`, então o app
mobile em produção (que não conhece o campo) continua inserindo e lendo
lojas como antes.

Downgrade: remove a coluna.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lojas",
        sa.Column("horario_fechamento", sa.Time(), nullable=False, server_default=sa.text("'21:00:00'")),
    )


def downgrade() -> None:
    op.drop_column("lojas", "horario_fechamento")
