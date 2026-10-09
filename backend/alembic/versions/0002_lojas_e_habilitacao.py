"""adiciona lojas e habilitacao produto-loja (recriacao completa)

ID da revisão: 0002
Revisa: 0001
Criada em: 2026-06-27

Esta migração é DESTRUTIVA de propósito: como o projeto está em fase de
desenvolvimento, com apenas dados de teste, optamos por apagar e recriar
toda a estrutura afetada em vez de escrever uma transformação de dados
que não traria valor real. NÃO use esta abordagem em um banco com dados
de produção reais — nesse caso, seria necessário migrar os dados
existentes em vez de apagá-los.

Mudanças principais:
- Nova tabela `lojas` (negócio pode ter múltiplas lojas).
- Nova tabela `produtos_lojas` (habilitação: quais produtos cada loja
  pode contar).
- `negocios` perde `horario_zeragem` (passa a ser por loja).
- `usuarios` ganha `loja_id` (cada usuário pertence a uma loja fixa).
- `estoque_atual` e `historico_contagens` ganham `loja_id`, e a
  unicidade de `estoque_atual` passa a ser sobre (produto_id, loja_id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Apaga, na ordem certa (respeitando dependências de FK), as tabelas
    # que serão recriadas com a nova estrutura. Dados de teste apenas.
    op.drop_table("historico_contagens")
    op.drop_table("estoque_atual")
    op.drop_table("permissoes_web")
    op.drop_table("usuarios")
    op.drop_table("produtos")
    op.drop_table("negocios")
    sa.Enum(name="statususuario").drop(op.get_bind(), checkfirst=True)

    # ---- negocios (recriada, sem horario_zeragem) ----
    op.create_table(
        "negocios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ---- lojas (nova) ----
    op.create_table(
        "lojas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("horario_zeragem", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_lojas_negocio_id", "lojas", ["negocio_id"])

    # ---- usuarios (recriada, com loja_id) ----
    status_usuario_enum = sa.Enum("ativo", "bloqueado", name="statususuario")
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("status", status_usuario_enum, nullable=False, server_default="ativo"),
        sa.Column("tem_acesso_app", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # ---- permissoes_web (recriada, estrutura igual à anterior) ----
    op.create_table(
        "permissoes_web",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("pagina_ou_modulo", sa.String(length=100), nullable=False),
    )
    op.create_index("ix_permissoes_web_usuario_id", "permissoes_web", ["usuario_id"])
    op.create_index("ix_usuarios_negocio_id", "usuarios", ["negocio_id"])
    op.create_index("ix_usuarios_loja_id", "usuarios", ["loja_id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    # ---- produtos (recriada, estrutura igual à anterior) ----
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

    # ---- produtos_lojas (nova: tabela de habilitação) ----
    op.create_table(
        "produtos_lojas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("produto_id", "loja_id", name="uq_produto_loja"),
    )
    op.create_index("ix_produtos_lojas_produto_id", "produtos_lojas", ["produto_id"])
    op.create_index("ix_produtos_lojas_loja_id", "produtos_lojas", ["loja_id"])

    # ---- estoque_atual (recriada, com loja_id e unicidade composta) ----
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
    op.create_index("ix_estoque_atual_produto_id", "estoque_atual", ["produto_id"])
    op.create_index("ix_estoque_atual_loja_id", "estoque_atual", ["loja_id"])
    op.create_index("ix_estoque_atual_negocio_id", "estoque_atual", ["negocio_id"])

    # ---- historico_contagens (recriada, com loja_id) ----
    op.create_table(
        "historico_contagens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_historico_contagens_produto_id", "historico_contagens", ["produto_id"])
    op.create_index("ix_historico_contagens_loja_id", "historico_contagens", ["loja_id"])
    op.create_index("ix_historico_contagens_negocio_id", "historico_contagens", ["negocio_id"])
    op.create_index("ix_historico_contagens_data_referencia", "historico_contagens", ["data_referencia"])


def downgrade() -> None:
    # Downgrade também é destrutivo, pelo mesmo motivo do upgrade: estamos
    # em fase de desenvolvimento, sem dados reais a preservar.
    op.drop_table("historico_contagens")
    op.drop_table("estoque_atual")
    op.drop_table("produtos_lojas")
    op.drop_table("produtos")
    op.drop_table("usuarios")
    op.drop_table("lojas")
    op.drop_table("negocios")
    sa.Enum(name="statususuario").drop(op.get_bind(), checkfirst=True)

    # Recria a estrutura antiga (equivalente à migração 0001), para manter
    # o downgrade consistente caso seja usado.
    op.create_table(
        "negocios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("horario_zeragem", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
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
    op.create_table(
        "estoque_atual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False, unique=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "historico_contagens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("data_referencia", sa.DateTime(), nullable=False),
    )
