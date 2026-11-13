"""lançamentos de perda pela loja (D110)

ID da revisão: 0026
Revisa: 0025
Criada em: 2026-11-11

O supermercado em geral não registra perda (análise de 07/11/2026), então
a perda passa a ser lançada no Frescor: a loja lança no app, no momento do
descarte, e o gestor vê e corrige no SaaS (D110). Cada lançamento fica
guardado com motivo, quem e quando; a soma do dia vira a perda do dia em
`perdas_diarias` (origem `manual`), que previsão, necessidade e consultas
já leem.

Tabela nova `lancamentos_perda` e enum `motivoperda`. Nada muda nas tabelas
existentes (o app em produção não é afetado).

Downgrade: apaga a tabela e o enum. As linhas de `perdas_diarias` geradas
pelos lançamentos continuam lá (são a perda do dia; o código antigo as lê
como perda importada).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MOTIVOS = ("vencido", "avariado", "outro")


def upgrade() -> None:
    motivo = postgresql.ENUM(*MOTIVOS, name="motivoperda", create_type=False)
    motivo.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "lancamentos_perda",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.Column("motivo", motivo, nullable=False),
        sa.Column("observacao", sa.String(200), nullable=True),
        sa.Column("lancado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("lancado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("alterado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("alterado_em", sa.DateTime(), nullable=True),
        sa.CheckConstraint("quantidade > 0", name="ck_lancamento_perda_quantidade_positiva"),
        sa.ForeignKeyConstraint(["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"],
                                name="fk_lancamento_perda_negocio_loja"),
        sa.ForeignKeyConstraint(["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
                                name="fk_lancamento_perda_negocio_produto"),
    )
    op.create_index("ix_lancamentos_perda_negocio_id", "lancamentos_perda", ["negocio_id"])
    op.create_index("ix_lancamentos_perda_loja_data", "lancamentos_perda", ["loja_id", "data"])
    op.create_index("ix_lancamentos_perda_produto_id", "lancamentos_perda", ["produto_id"])


def downgrade() -> None:
    op.drop_index("ix_lancamentos_perda_produto_id", table_name="lancamentos_perda")
    op.drop_index("ix_lancamentos_perda_loja_data", table_name="lancamentos_perda")
    op.drop_index("ix_lancamentos_perda_negocio_id", table_name="lancamentos_perda")
    op.drop_table("lancamentos_perda")
    postgresql.ENUM(name="motivoperda").drop(op.get_bind(), checkfirst=True)
