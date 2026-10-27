"""setores de produção (bolo, biscoito, pão...) e setor do produto (D67)

ID da revisão: 0023
Revisa: 0022
Criada em: 2026-10-15

Fase 4 / N9b. O setor é a divisão da produção DENTRO de uma central (a
bancada de pães, a de bolos...), diferente da seção da D14 (padaria,
açougue: a central inteira). Serve para imprimir a ordem aprovada com uma
folha por setor.

- `setores_producao`: por central (nome, ordem de exibição, ativo). Nome
  único dentro da central. FK composta com a central do mesmo negócio.
- `produtos.setor_producao_id`: opcional (produto sem setor sai na folha
  "Sem setor"). FK composta (negocio_id, setor) -> setor do mesmo negócio;
  com NULL a FK não é verificada (MATCH SIMPLE), que é o que se quer aqui.
  Coluna nullable: o app mobile em produção não é afetado.

Downgrade: remove a coluna do produto e a tabela.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "setores_producao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("central_producao_id", sa.Integer(), sa.ForeignKey("centrais_producao.id"), nullable=False),
        sa.Column("nome", sa.String(length=80), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("negocio_id", "id", name="uq_setor_negocio_id"),
        sa.UniqueConstraint("central_producao_id", "nome", name="uq_setor_central_nome"),
        sa.CheckConstraint("btrim(nome) <> ''", name="ck_setor_nome_preenchido"),
        sa.ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"], ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_setor_negocio_central",
        ),
    )
    op.create_index("ix_setores_central", "setores_producao", ["negocio_id", "central_producao_id"])

    op.add_column("produtos", sa.Column("setor_producao_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "produtos_setor_producao_id_fkey", "produtos", "setores_producao", ["setor_producao_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_produto_negocio_setor", "produtos", "setores_producao",
        ["negocio_id", "setor_producao_id"], ["negocio_id", "id"],
    )
    op.create_index("ix_produtos_setor_producao_id", "produtos", ["setor_producao_id"])


def downgrade() -> None:
    op.drop_index("ix_produtos_setor_producao_id", table_name="produtos")
    op.drop_constraint("fk_produto_negocio_setor", "produtos", type_="foreignkey")
    op.drop_constraint("produtos_setor_producao_id_fkey", "produtos", type_="foreignkey")
    op.drop_column("produtos", "setor_producao_id")
    op.drop_index("ix_setores_central", table_name="setores_producao")
    op.drop_table("setores_producao")
