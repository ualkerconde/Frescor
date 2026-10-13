"""cria vendas_diarias e perdas_diarias; adiciona lojas.codigo

ID da revisão: 0015
Revisa: 0014
Criada em: 2026-10-13

Fase 2 (ingestão de vendas e perdas), passo P2. Decisões em docs/STATUS.md:

- `vendas_diarias` e `perdas_diarias`: uma linha por loja + produto + dia
  + origem. Têm `negocio_id` (D2: tabelas compartilhadas, `negocio_id` em
  todas). `quantidade` está na unidade do produto (D6: UN -> peças, KG ->
  kg), Numeric(12,3), e não pode ser negativa.
- Chave única (loja_id, produto_id, data, origem): reimportar o mesmo dia
  da mesma origem SUBSTITUI o valor (D5, via INSERT ... ON CONFLICT DO
  UPDATE no serviço de importação). Origens diferentes (ex.: `manual` e
  `api`) do mesmo dia coexistem. A chave também serve de índice para as
  consultas por loja + produto + período.
- Enums: `origemvenda` (api, manual) e `origemperda` (api, manual,
  inferida). `inferida` já nasce aqui para a Fase 8 não precisar alterar
  o enum.
- `lojas.codigo` (opcional, único dentro do negócio): identifica a loja no
  CSV de importação (D7, provisória). Nullable para não afetar as lojas
  existentes nem o app mobile.
- Garantia de negócio no banco: FKs compostas (negocio_id, loja_id) ->
  lojas(negocio_id, id) e (negocio_id, produto_id) -> produtos(negocio_id,
  id). Assim uma venda/perda nunca aponta para loja ou produto de outro
  negócio, mesmo que um serviço erre. Para isso, `lojas` e `produtos`
  ganham a única (negocio_id, id) -- sempre satisfeita, porque `id` já é
  único; ela só existe para servir de alvo das FKs compostas. Não muda nada
  para o app mobile.

Esta migração NÃO é destrutiva -- cria tabelas, uma coluna nova e
constraints únicas que os dados existentes já satisfazem.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

origem_venda_enum = sa.Enum("api", "manual", name="origemvenda")
origem_perda_enum = sa.Enum("api", "manual", "inferida", name="origemperda")


def _criar_tabela(nome: str, enum_nome: str, prefixo: str) -> None:
    op.create_table(
        nome,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.Column("origem", PgEnum(name=enum_nome, create_type=False), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("loja_id", "produto_id", "data", "origem", name=f"uq_{prefixo}_loja_produto_data_origem"),
        sa.ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name=f"fk_{prefixo}_negocio_loja",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name=f"fk_{prefixo}_negocio_produto",
        ),
        sa.CheckConstraint("quantidade >= 0", name=f"ck_{prefixo}_quantidade_nao_negativa"),
    )
    op.create_index(f"ix_{nome}_negocio_id", nome, ["negocio_id"])
    op.create_index(f"ix_{nome}_produto_id", nome, ["produto_id"])


def upgrade() -> None:
    origem_venda_enum.create(op.get_bind(), checkfirst=True)
    origem_perda_enum.create(op.get_bind(), checkfirst=True)

    # Alvos das FKs compostas (precisam existir antes das tabelas).
    op.create_unique_constraint("uq_loja_negocio_id", "lojas", ["negocio_id", "id"])
    op.create_unique_constraint("uq_produto_negocio_id", "produtos", ["negocio_id", "id"])

    _criar_tabela("vendas_diarias", "origemvenda", "venda")
    _criar_tabela("perdas_diarias", "origemperda", "perda")

    op.add_column("lojas", sa.Column("codigo", sa.String(length=32), nullable=True))
    op.create_unique_constraint("uq_loja_negocio_codigo", "lojas", ["negocio_id", "codigo"])


def downgrade() -> None:
    op.drop_constraint("uq_loja_negocio_codigo", "lojas", type_="unique")
    op.drop_column("lojas", "codigo")

    op.drop_index("ix_perdas_diarias_produto_id", table_name="perdas_diarias")
    op.drop_index("ix_perdas_diarias_negocio_id", table_name="perdas_diarias")
    op.drop_table("perdas_diarias")
    op.drop_index("ix_vendas_diarias_produto_id", table_name="vendas_diarias")
    op.drop_index("ix_vendas_diarias_negocio_id", table_name="vendas_diarias")
    op.drop_table("vendas_diarias")

    op.drop_constraint("uq_produto_negocio_id", "produtos", type_="unique")
    op.drop_constraint("uq_loja_negocio_id", "lojas", type_="unique")

    origem_perda_enum.drop(op.get_bind(), checkfirst=True)
    origem_venda_enum.drop(op.get_bind(), checkfirst=True)
