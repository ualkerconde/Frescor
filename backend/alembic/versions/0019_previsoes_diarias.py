"""cria previsoes_diarias (previsões gravadas, D22)

ID da revisão: 0019
Revisa: 0018
Criada em: 2026-10-14

Fase 3 / F7. Previsão de venda gravada por loja + produto + dia, com os
componentes que a explicam, a versão do método e quem/quando gerou (ver o
docstring de app/models/previsao_diaria.py).

- Chave única (loja_id, produto_id, data): uma previsão por dia; gerar de
  novo substitui (o serviço apaga e grava na mesma transação).
- FKs compostas (negocio_id, loja_id/produto_id/central_producao_id) para
  as tabelas do mesmo negócio (D2), como em vendas_diarias.
- Checks: previsão não negativa; peso do histórico entre 0 e 1; dia
  previsto depois da data de referência.
- Enums novos: metodoprevisao, estatisticabase, origemproxy.
- Índice (negocio_id, central_producao_id, data) para a consulta da tela.

Esta migração NÃO é destrutiva -- só cria uma tabela e três enums. Nenhuma
tabela usada pelo app mobile é alterada.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

metodo_enum = sa.Enum("semanal", "sazonal", name="metodoprevisao")
estatistica_enum = sa.Enum("mediana", "media", "media_aparada", name="estatisticabase")
origem_proxy_enum = sa.Enum("outras_lojas", "categoria", "unidade", name="origemproxy")


def upgrade() -> None:
    for enum_ in (metodo_enum, estatistica_enum, origem_proxy_enum):
        enum_.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "previsoes_diarias",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("central_producao_id", sa.Integer(), sa.ForeignKey("centrais_producao.id"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("previsao", sa.Numeric(14, 4), nullable=True),
        sa.Column("previsao_sem_evento", sa.Numeric(14, 4), nullable=True),
        sa.Column("previsao_propria", sa.Numeric(14, 4), nullable=True),
        sa.Column("metodo", PgEnum(name="metodoprevisao", create_type=False), nullable=False),
        sa.Column("estatistica", PgEnum(name="estatisticabase", create_type=False), nullable=False),
        sa.Column("base", sa.Numeric(14, 4), nullable=True),
        sa.Column("semanas_na_base", sa.Integer(), nullable=False),
        sa.Column("tendencia", sa.Numeric(8, 4), nullable=False),
        sa.Column("tendencia_bruta", sa.Numeric(14, 4), nullable=True),
        sa.Column("dias_na_tendencia", sa.Integer(), nullable=False),
        sa.Column("inicio_historico", sa.Date(), nullable=True),
        sa.Column("peso_historico", sa.Numeric(6, 4), nullable=False),
        sa.Column("proxy", sa.Numeric(14, 4), nullable=True),
        sa.Column("origem_proxy", PgEnum(name="origemproxy", create_type=False), nullable=True),
        sa.Column("eventos", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("versao_metodo", sa.String(length=32), nullable=False),
        sa.Column("gerado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("gerado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.UniqueConstraint("loja_id", "produto_id", "data", name="uq_previsao_loja_produto_data"),
        sa.CheckConstraint("previsao IS NULL OR previsao >= 0", name="ck_previsao_nao_negativa"),
        sa.CheckConstraint("peso_historico >= 0 AND peso_historico <= 1", name="ck_previsao_peso_0_a_1"),
        sa.CheckConstraint("data > data_referencia", name="ck_previsao_data_depois_da_referencia"),
        sa.ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_previsao_negocio_loja"
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_previsao_negocio_produto"
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"],
            ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_previsao_negocio_central",
        ),
    )
    op.create_index("ix_previsoes_central_data", "previsoes_diarias", ["negocio_id", "central_producao_id", "data"])


def downgrade() -> None:
    op.drop_index("ix_previsoes_central_data", table_name="previsoes_diarias")
    op.drop_table("previsoes_diarias")
    for enum_ in (origem_proxy_enum, estatistica_enum, metodo_enum):
        enum_.drop(op.get_bind(), checkfirst=True)
