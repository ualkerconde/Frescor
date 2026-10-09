"""adiciona unidade de medida, peso medio e separa estoque em rascunho/calculado

ID da revisão: 0003
Revisa: 0002
Criada em: 2026-06-27

Esta migração é DESTRUTIVA de propósito, pelo mesmo motivo das anteriores:
o projeto está em fase de desenvolvimento, com apenas dados de teste.

Mudanças:
- `produtos` ganha `unidade_medida` (enum UN/KG) e `peso_medio_kg`
  (obrigatório só para produtos em KG, validado na camada de serviço).
- `estoque_atual.quantidade` é substituído por dois campos:
  `quantidade_inventariada` (o antigo rascunho, mesmo papel de antes) e
  `estoque_atual_calculado` (novo: valor real, calculado a partir da
  contagem e da unidade de medida/peso médio do produto).
- `historico_contagens.quantidade` é substituído por
  `quantidade_inventariada` + `estoque_atual_calculado`, pelo mesmo motivo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- produtos: novas colunas ----
    unidade_medida_enum = sa.Enum("UN", "KG", name="unidademedida")
    unidade_medida_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "produtos",
        sa.Column("unidade_medida", unidade_medida_enum, nullable=False, server_default="UN"),
    )
    op.add_column("produtos", sa.Column("peso_medio_kg", sa.Numeric(10, 4), nullable=True))

    # ---- estoque_atual: apaga e recria com os dois campos de estoque ----
    # (Dados de teste apenas — recriação simples em vez de migrar valores.)
    op.drop_table("estoque_atual")
    op.create_table(
        "estoque_atual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade_inventariada", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estoque_atual_calculado", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("produto_id", "loja_id", name="uq_estoque_produto_loja"),
    )
    op.create_index("ix_estoque_atual_produto_id", "estoque_atual", ["produto_id"])
    op.create_index("ix_estoque_atual_loja_id", "estoque_atual", ["loja_id"])
    op.create_index("ix_estoque_atual_negocio_id", "estoque_atual", ["negocio_id"])

    # ---- historico_contagens: apaga e recria com os dois campos ----
    op.drop_table("historico_contagens")
    op.create_table(
        "historico_contagens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade_inventariada", sa.Integer(), nullable=False),
        sa.Column("estoque_atual_calculado", sa.Numeric(12, 4), nullable=False),
        sa.Column("data_referencia", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_historico_contagens_produto_id", "historico_contagens", ["produto_id"])
    op.create_index("ix_historico_contagens_loja_id", "historico_contagens", ["loja_id"])
    op.create_index("ix_historico_contagens_negocio_id", "historico_contagens", ["negocio_id"])
    op.create_index("ix_historico_contagens_data_referencia", "historico_contagens", ["data_referencia"])


def downgrade() -> None:
    op.drop_table("historico_contagens")
    op.create_table(
        "historico_contagens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.DateTime(), nullable=False),
    )

    op.drop_table("estoque_atual")
    op.create_table(
        "estoque_atual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("produto_id", "loja_id", name="uq_estoque_produto_loja"),
    )

    op.drop_column("produtos", "peso_medio_kg")
    op.drop_column("produtos", "unidade_medida")
    sa.Enum(name="unidademedida").drop(op.get_bind(), checkfirst=True)
