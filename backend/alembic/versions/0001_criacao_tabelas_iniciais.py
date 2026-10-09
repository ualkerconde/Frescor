"""criacao das tabelas iniciais

ID da revisão: 0001
Revisa: None
Criada em: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# identificadores usados pelo Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- negocios ----
    op.create_table(
        "negocios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("horario_zeragem", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ---- usuarios ----
    status_usuario_enum = sa.Enum("ativo", "bloqueado", name="statususuario")
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("status", status_usuario_enum, nullable=False, server_default="ativo"),
        sa.Column("tem_acesso_app", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usuarios_negocio_id", "usuarios", ["negocio_id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    # ---- permissoes_web ----
    op.create_table(
        "permissoes_web",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("pagina_ou_modulo", sa.String(length=100), nullable=False),
    )
    op.create_index("ix_permissoes_web_usuario_id", "permissoes_web", ["usuario_id"])

    # ---- produtos ----
    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("codigo_barras", sa.String(length=64), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_produtos_negocio_id", "produtos", ["negocio_id"])
    op.create_index("ix_produtos_codigo_barras", "produtos", ["codigo_barras"])

    # ---- estoque_atual ----
    op.create_table(
        "estoque_atual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False, unique=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_estoque_atual_produto_id", "estoque_atual", ["produto_id"], unique=True)
    op.create_index("ix_estoque_atual_negocio_id", "estoque_atual", ["negocio_id"])

    # ---- historico_contagens ----
    op.create_table(
        "historico_contagens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_historico_contagens_produto_id", "historico_contagens", ["produto_id"])
    op.create_index("ix_historico_contagens_negocio_id", "historico_contagens", ["negocio_id"])
    op.create_index("ix_historico_contagens_data_referencia", "historico_contagens", ["data_referencia"])


def downgrade() -> None:
    op.drop_table("historico_contagens")
    op.drop_table("estoque_atual")
    op.drop_table("produtos")
    op.drop_table("permissoes_web")
    op.drop_table("usuarios")
    op.drop_table("negocios")
    sa.Enum(name="statususuario").drop(op.get_bind(), checkfirst=True)
