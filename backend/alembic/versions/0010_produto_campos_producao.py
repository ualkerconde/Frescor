"""adiciona campos de producao em produtos

ID da revisão: 0010
Revisa: 0009
Criada em: 2026-08-20

Novos campos na tabela `produtos` para suportar os módulos de produção e
distribuição centralizada:

- `tem_producao_propria`: diferencia produto fabricado na central de item
  apenas distribuído. Default false para não quebrar produtos existentes.
- `dias_validade`: prazo de validade em dias após a fabricação (opcional).
- `margem_maxima_percentual`: percentual sobre o estoque mínimo calculado
  para derivar o máximo. Usado na fase de cálculo de necessidade (futuro).
- `data_inicio_vigencia` / `data_fim_vigencia`: datas de vigência do
  produto. Nulos = produto permanente.
- `vigencia_recorrente`: true = sazonal (repete todo ano); false =
  descontinuado definitivamente após data_fim_vigencia. Default false.
- `ciclo_previsao` (enum: semanal | sazonal): ciclo de previsão de
  produção. Default semanal para não quebrar produtos existentes.

Esta migração NÃO remove nenhuma coluna existente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ciclo_previsao_enum = sa.Enum("semanal", "sazonal", name="cicloprevisao")


def upgrade() -> None:
    ciclo_previsao_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "produtos",
        sa.Column("tem_producao_propria", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "produtos",
        sa.Column("dias_validade", sa.Integer(), nullable=True),
    )
    op.add_column(
        "produtos",
        sa.Column("margem_maxima_percentual", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "produtos",
        sa.Column("data_inicio_vigencia", sa.Date(), nullable=True),
    )
    op.add_column(
        "produtos",
        sa.Column("data_fim_vigencia", sa.Date(), nullable=True),
    )
    op.add_column(
        "produtos",
        sa.Column("vigencia_recorrente", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "produtos",
        sa.Column(
            "ciclo_previsao",
            ciclo_previsao_enum,
            nullable=False,
            server_default="semanal",
        ),
    )


def downgrade() -> None:
    op.drop_column("produtos", "ciclo_previsao")
    op.drop_column("produtos", "vigencia_recorrente")
    op.drop_column("produtos", "data_fim_vigencia")
    op.drop_column("produtos", "data_inicio_vigencia")
    op.drop_column("produtos", "margem_maxima_percentual")
    op.drop_column("produtos", "dias_validade")
    op.drop_column("produtos", "tem_producao_propria")
    ciclo_previsao_enum.drop(op.get_bind(), checkfirst=True)
