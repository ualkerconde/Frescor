"""adiciona tipo_usuario e central_producao_id em usuarios

ID da revisão: 0009
Revisa: 0008
Criada em: 2026-08-20

Suporte ao perfil de gestor da central de produção:

- `tipo_usuario` (enum): distingue `operador_loja` (perfil atual, sem
  quebra) de `gestor_central` (novo perfil do painel web). Default
  `operador_loja` para que todos os usuários existentes continuem válidos.

- `loja_id` passa a ser nullable: operadores de loja ainda têm loja_id
  preenchido; gestores de central terão loja_id = NULL.

- `central_producao_id` (nullable): preenchido apenas para gestores.

Adicionado também um check constraint de banco para garantir a regra:
  operador_loja  -> loja_id NOT NULL e central_producao_id NULL
  gestor_central -> central_producao_id NOT NULL e loja_id NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum criado explicitamente no PostgreSQL (não usa create_type via sa.Enum inline).
tipo_usuario_enum = sa.Enum("operador_loja", "gestor_central", name="tipousuario")


def upgrade() -> None:
    # Cria o tipo enum no PostgreSQL antes de usá-lo.
    tipo_usuario_enum.create(op.get_bind(), checkfirst=True)

    # Adiciona tipo_usuario com default operador_loja (não quebra usuários existentes).
    op.add_column(
        "usuarios",
        sa.Column(
            "tipo_usuario",
            tipo_usuario_enum,
            nullable=False,
            server_default="operador_loja",
        ),
    )

    # Torna loja_id nullable (gestores de central não têm loja fixa).
    op.alter_column("usuarios", "loja_id", nullable=True)

    # Adiciona central_producao_id (somente gestores de central).
    op.add_column(
        "usuarios",
        sa.Column(
            "central_producao_id",
            sa.Integer(),
            sa.ForeignKey("centrais_producao.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_usuarios_central_producao_id", "usuarios", ["central_producao_id"])

    # Check constraint: garante a integridade entre tipo e chaves estrangeiras.
    op.create_check_constraint(
        "ck_usuario_tipo_vs_loja_central",
        "usuarios",
        "(tipo_usuario = 'operador_loja' AND loja_id IS NOT NULL AND central_producao_id IS NULL) OR "
        "(tipo_usuario = 'gestor_central' AND central_producao_id IS NOT NULL AND loja_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_usuario_tipo_vs_loja_central", "usuarios", type_="check")
    op.drop_index("ix_usuarios_central_producao_id", table_name="usuarios")
    op.drop_column("usuarios", "central_producao_id")
    op.alter_column("usuarios", "loja_id", nullable=False)
    op.drop_column("usuarios", "tipo_usuario")
    tipo_usuario_enum.drop(op.get_bind(), checkfirst=True)
