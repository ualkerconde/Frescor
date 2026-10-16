"""seção e prazo de entrega na central; tipo de abastecimento no produto; negócio no calendário

ID da revisão: 0020
Revisa: 0019
Criada em: 2026-10-15

Fase 4 / N1. Decisões D14, D32 e D40 (`docs/STATUS.md`).

Upgrade:
1. `centrais_producao.secao` (enum `secaocentral`: padaria, acougue,
   hortifruti), NOT NULL com padrão `padaria`: cada central atende uma
   seção só (D14). As centrais existentes ficam como padaria (o primeiro
   cliente é só padaria).
2. `centrais_producao.prazo_entrega_dias` (inteiro, NOT NULL, padrão 0,
   check >= 0): dias entre a produção e a entrega na loja (D32). A
   central produz no dia D e entrega em D (0); rede grande pode usar 1.
3. `produtos.tipo_abastecimento` (enum `tipoabastecimento`: produzido,
   distribuido), preenchido a partir de `tem_producao_propria`
   (true -> produzido, false -> distribuido), que é removida (D40).
   Padrão `produzido` para produto novo sem tipo: um produto sem tipo
   aparece na ordem de produção, onde o gestor vê; como "distribuído"
   ficaria fora da ordem sem ninguém notar. Nenhum código do `app/` lia
   `tem_producao_propria` (conferido em 2026-10-15); só o `seed_produtos.py`,
   atualizado junto.
4. `calendario_producao.negocio_id`, preenchido a partir do produto,
   NOT NULL, com FK composta (negocio_id, produto_id) -> produtos
   (regra de ouro 1: toda query filtra por negócio; antes só dava pelo
   JOIN com o produto). NOT NULL apesar da regra de colunas novas: com
   NULL a FK composta não é verificada (MATCH SIMPLE). Nenhuma versão do
   app grava no calendário (só o seed).

Downgrade: recria `tem_producao_propria` a partir do tipo e desfaz o
resto na ordem inversa, removendo os dois enums.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

secao_enum = sa.Enum("padaria", "acougue", "hortifruti", name="secaocentral")
tipo_abastecimento_enum = sa.Enum("produzido", "distribuido", name="tipoabastecimento")


def upgrade() -> None:
    bind = op.get_bind()
    secao_enum.create(bind, checkfirst=True)
    tipo_abastecimento_enum.create(bind, checkfirst=True)

    # ---- centrais_producao: seção e prazo de entrega ----
    op.add_column(
        "centrais_producao",
        sa.Column(
            "secao", PgEnum(name="secaocentral", create_type=False),
            nullable=False, server_default="padaria",
        ),
    )
    op.add_column(
        "centrais_producao",
        sa.Column("prazo_entrega_dias", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_central_prazo_entrega_nao_negativo", "centrais_producao", "prazo_entrega_dias >= 0"
    )

    # ---- produtos: tipo de abastecimento no lugar de tem_producao_propria ----
    op.add_column(
        "produtos",
        sa.Column("tipo_abastecimento", PgEnum(name="tipoabastecimento", create_type=False), nullable=True),
    )
    op.execute(sa.text("""
        UPDATE produtos SET tipo_abastecimento =
            CASE WHEN tem_producao_propria THEN 'produzido' ELSE 'distribuido' END::tipoabastecimento
    """))
    op.alter_column("produtos", "tipo_abastecimento", nullable=False, server_default="produzido")
    op.drop_column("produtos", "tem_producao_propria")

    # ---- calendario_producao: negocio_id com FK composta ----
    op.add_column("calendario_producao", sa.Column("negocio_id", sa.Integer(), nullable=True))
    op.execute(sa.text("""
        UPDATE calendario_producao c SET negocio_id = p.negocio_id
        FROM produtos p WHERE p.id = c.produto_id
    """))
    op.alter_column("calendario_producao", "negocio_id", nullable=False)
    op.create_foreign_key(
        "calendario_producao_negocio_id_fkey", "calendario_producao", "negocios", ["negocio_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_calendario_negocio_produto", "calendario_producao", "produtos",
        ["negocio_id", "produto_id"], ["negocio_id", "id"],
    )
    op.create_index("ix_calendario_producao_negocio_id", "calendario_producao", ["negocio_id"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_calendario_producao_negocio_id", table_name="calendario_producao")
    op.drop_constraint("fk_calendario_negocio_produto", "calendario_producao", type_="foreignkey")
    op.drop_constraint("calendario_producao_negocio_id_fkey", "calendario_producao", type_="foreignkey")
    op.drop_column("calendario_producao", "negocio_id")

    op.add_column(
        "produtos",
        sa.Column("tem_producao_propria", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text("UPDATE produtos SET tem_producao_propria = (tipo_abastecimento = 'produzido')"))
    op.drop_column("produtos", "tipo_abastecimento")

    op.drop_constraint("ck_central_prazo_entrega_nao_negativo", "centrais_producao", type_="check")
    op.drop_column("centrais_producao", "prazo_entrega_dias")
    op.drop_column("centrais_producao", "secao")

    tipo_abastecimento_enum.drop(bind, checkfirst=True)
    secao_enum.drop(bind, checkfirst=True)
