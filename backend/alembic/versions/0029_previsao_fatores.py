"""fatores de calendário gravados na previsão (D112–D114)

ID da revisão: 0029
Revisa: 0028
Criada em: 2026-11-13

A previsão semanal passou a multiplicar base × tendência pelos fatores de
calendário (ano anterior, semana do mês, dia do mês, feriado nacional;
VERSAO_METODO 2026.11-v3). Para a tela explicar a conta e para comparar
versões do motor, os fatores ficam gravados ao lado dos outros componentes.

Coluna nova, nullable (o app mobile não lê esta tabela):
- `previsoes_diarias.fatores` (JSONB): {"ano", "semana_mes", "dia_mes",
  "feriado", "nome_feriado"}; os fatores como texto decimal ("1.0800").
  NULL nas previsões gravadas antes desta versão.

Downgrade: remove a coluna.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("previsoes_diarias", sa.Column("fatores", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("previsoes_diarias", "fatores")
