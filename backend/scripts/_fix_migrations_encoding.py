"""Script temporario para reescrever as migracoes 0012 e 0013 em UTF-8."""
import os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
versions = os.path.join(base, "alembic", "versions")

m0012 = """\
\"\"\"cria tabela calendario_producao

ID da revisao: 0012
Revisa: 0011
Criada em: 2026-08-20

Nova tabela `calendario_producao`: define em quais dias da semana cada
produto deve ser produzido pela central. Unicidade de (produto_id, dia_semana)
garantida por constraint de banco.

Nota: tipo enum criado via SQL cru; PgEnum(create_type=False) referencia
o tipo ja existente sem recria-lo.
Nome 'diasemana' = DiaSemana.__name__.lower() -- padrao SQLAlchemy.
\"\"\"
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
"""

m0013 = """\
\"\"\"cria eventos e tabelas de associacao evento_loja e evento_produto

ID da revisao: 0013
Revisa: 0012
Criada em: 2026-08-20

Tres novas tabelas para gerenciar periodos de demanda atipica (eventos):
- `eventos`, `eventos_lojas` (M2M), `eventos_produtos` (M2M).

Tipos enum criados via SQL cru com PgEnum(create_type=False) nas colunas.
Nomes seguem ClassName.__name__.lower():
  escopoloja    = EscopoLoja.__name__.lower()
  escopoproduto = EscopoProduto.__name__.lower()
  tipoajuste    = TipoAjuste.__name__.lower()

Esta migracao NAO e destrutiva -- apenas cria tabelas novas.
\"\"\"
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE TYPE escopoloja AS ENUM ('todas','especificas')"))
    op.execute(sa.text("CREATE TYPE escopoproduto AS ENUM ('todos','especificos')"))
    op.execute(sa.text("CREATE TYPE tipoajuste AS ENUM ('multiplicador','valor_fixo')"))

    # ---- eventos ----
    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("escopo_loja", PgEnum(name="escopoloja", create_type=False), nullable=False),
        sa.Column("escopo_produto", PgEnum(name="escopoproduto", create_type=False), nullable=False),
        sa.Column("tipo_ajuste", PgEnum(name="tipoajuste", create_type=False), nullable=False),
        sa.Column("valor_ajuste", sa.Numeric(10, 4), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_eventos_negocio_id", "eventos", ["negocio_id"])

    # ---- eventos_lojas (M2M) ----
    op.create_table(
        "eventos_lojas",
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("eventos.id"), primary_key=True),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), primary_key=True),
    )

    # ---- eventos_produtos (M2M) ----
    op.create_table(
        "eventos_produtos",
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("eventos.id"), primary_key=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("eventos_produtos")
    op.drop_table("eventos_lojas")
    op.drop_table("eventos")
    op.execute(sa.text("DROP TYPE IF EXISTS tipoajuste"))
    op.execute(sa.text("DROP TYPE IF EXISTS escopoproduto"))
    op.execute(sa.text("DROP TYPE IF EXISTS escopoloja"))
"""

for fname, content in [("0012_calendario_producao.py", m0012), ("0013_evento_e_associacoes.py", m0013)]:
    path = os.path.join(versions, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Gravado: {fname}")
