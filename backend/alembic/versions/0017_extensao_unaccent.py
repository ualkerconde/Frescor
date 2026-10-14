"""extensão unaccent para busca sem acento

ID da revisão: 0017
Revisa: 0016
Criada em: 2026-10-13

A busca de produtos do SaaS (GET /web/produtos) deve ignorar acentos e
maiúsculas: quem digita "pao" precisa achar "Pão". O PostgreSQL faz isso
com a extensão `unaccent` (vem com o PostgreSQL; é "trusted" desde a
versão 13, então o dono do banco pode criá-la sem ser superusuário).

Upgrade: CREATE EXTENSION IF NOT EXISTS (não falha se já existir).
Downgrade: DROP EXTENSION IF EXISTS, sem CASCADE -- se algum outro objeto
do banco passar a depender da extensão, o downgrade falha em vez de apagar
esse objeto. Atenção: se a extensão já existia ANTES desta migração, o
downgrade a remove mesmo assim (o banco de desenvolvimento não a tinha em
2026-10-13).

Esta migração NÃO é destrutiva -- apenas instala uma extensão.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS unaccent"))


def downgrade() -> None:
    op.execute(sa.text("DROP EXTENSION IF EXISTS unaccent"))
