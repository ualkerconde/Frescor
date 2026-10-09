"""adiciona niveis_classificacao e produto_classificacoes

ID da revisão: 0006
Revisa: 0005
Criada em: 2026-07-06

Suporte à classificação de produtos em até 4 níveis configuráveis por
negócio (tenant). Exemplos reais de uso, cada um definido pelo próprio
negócio (ver app/models/nivel_classificacao.py):

    Empresa A: Departamento -> Seção -> Categoria -> Subcategoria
    Empresa B: Setor
    Empresa C: Linha -> Família
    Empresa D: Categoria -> Subcategoria

Duas tabelas novas:
- `niveis_classificacao`: definição, por negócio, de até 4 níveis
  ordenados (1 a 4) com nome configurável.
- `produto_classificacoes`: valor atribuído a um produto para um nível
  específico (produto_id, nivel_id) -> valor.

Esta migração NÃO é destrutiva — apenas cria tabelas novas, sem afetar
nenhuma tabela ou dado existente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- niveis_classificacao (nova) ----
    op.create_table(
        "niveis_classificacao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("negocio_id", "ordem", name="uq_nivel_negocio_ordem"),
        sa.CheckConstraint("ordem >= 1 AND ordem <= 4", name="ck_nivel_ordem_1_a_4"),
    )
    op.create_index("ix_niveis_classificacao_negocio_id", "niveis_classificacao", ["negocio_id"])

    # ---- produto_classificacoes (nova) ----
    op.create_table(
        "produto_classificacoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("nivel_id", sa.Integer(), sa.ForeignKey("niveis_classificacao.id"), nullable=False),
        sa.Column("valor", sa.String(length=255), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("produto_id", "nivel_id", name="uq_produto_classificacao_nivel"),
    )
    op.create_index("ix_produto_classificacoes_produto_id", "produto_classificacoes", ["produto_id"])
    op.create_index("ix_produto_classificacoes_nivel_id", "produto_classificacoes", ["nivel_id"])


def downgrade() -> None:
    op.drop_table("produto_classificacoes")
    op.drop_table("niveis_classificacao")
