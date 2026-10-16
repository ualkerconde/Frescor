"""ordens de produção: ordem, itens por produto e linhas por loja

ID da revisão: 0022
Revisa: 0021
Criada em: 2026-10-15

Fase 4 / N5 (doc §3.8, §3.9; decisões D38, D39, D43, D52).

- `ordens_producao`: a ordem do dia de uma central. Situação `rascunho`
  (gerada, editável, pode ser regerada) ou `aprovada` (travada; vira
  trânsito para as próximas ordens, D43). Tipo `programada` (ciclo normal)
  ou `emergencial` (Fase 8). No máximo UMA programada por central e data de
  produção (índice único parcial). `data_entrega` é gravada na geração (D +
  prazo da central): se o prazo mudar depois, a ordem antiga não muda.
  Guarda a versão do método da necessidade, a data de referência da
  previsão usada e quem/quando gerou e aprovou (aprovada exige os dois;
  rascunho não tem nenhum).
- `ordens_producao_itens`: um por produto na ordem, com o tipo de
  abastecimento e a unidade daquele momento (D39: a ordem guarda os dois
  tipos; a tela de produção mostra só os produzidos). A quantidade
  planejada NÃO é gravada aqui: é a soma das linhas, para nunca divergir.
  `quantidade_produzida` fica para a Fase 5 (produção real).
- `ordens_producao_linhas`: uma por loja em cada item. `quantidade_sugerida`
  (do cálculo; NULL quando não havia como calcular: sem previsão, sem
  calendário...) e `quantidade_final` (do gestor; NULL = ainda não
  informada). `componentes` (JSON) guarda a conta inteira para o "Ver a
  conta" e para a Fase 7 (sugestão × decisão); `avisos` (JSON) à parte,
  para a tela filtrar. Edição: quem, quando e motivo opcional. Recebimento
  (Fase 5): `quantidade_recebida` e `recebido_em`; linha de ordem aprovada
  com `recebido_em` NULL é trânsito (D43).

Isolamento (D2): `negocio_id` em todas, com FKs compostas para central,
ordem, item, produto e loja do mesmo negócio. Que a loja seja da central
da ordem é regra do serviço (o vínculo loja-central pode mudar com o tempo).

Apagar a ordem apaga itens e linhas (ON DELETE CASCADE): é assim que o
rascunho é regerado (N6).

Downgrade: remove as três tabelas e os dois enums.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

status_enum = sa.Enum("rascunho", "aprovada", name="statusordemproducao")
tipo_enum = sa.Enum("programada", "emergencial", name="tipoordemproducao")


def upgrade() -> None:
    for enum_ in (status_enum, tipo_enum):
        enum_.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ordens_producao",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("central_producao_id", sa.Integer(), sa.ForeignKey("centrais_producao.id"), nullable=False),
        sa.Column("data_producao", sa.Date(), nullable=False),
        sa.Column("data_entrega", sa.Date(), nullable=False),
        sa.Column("tipo", PgEnum(name="tipoordemproducao", create_type=False), nullable=False,
                  server_default="programada"),
        sa.Column("status", PgEnum(name="statusordemproducao", create_type=False), nullable=False,
                  server_default="rascunho"),
        sa.Column("versao_metodo", sa.String(length=32), nullable=False),
        sa.Column("referencia_previsao", sa.Date(), nullable=True),
        sa.Column("gerado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("gerado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("aprovado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.UniqueConstraint("negocio_id", "id", name="uq_ordem_negocio_id"),
        sa.CheckConstraint("data_entrega >= data_producao", name="ck_ordem_entrega_depois_da_producao"),
        sa.CheckConstraint(
            "(status = 'aprovada' AND aprovado_em IS NOT NULL AND aprovado_por_usuario_id IS NOT NULL)"
            " OR (status = 'rascunho' AND aprovado_em IS NULL AND aprovado_por_usuario_id IS NULL)",
            name="ck_ordem_aprovacao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"], ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_ordem_negocio_central",
        ),
    )
    op.create_index("ix_ordens_central_data", "ordens_producao", ["negocio_id", "central_producao_id", "data_producao"])
    op.create_index(
        "uq_ordem_programada_central_data", "ordens_producao", ["central_producao_id", "data_producao"],
        unique=True, postgresql_where=sa.text("tipo = 'programada'"),
    )

    op.create_table(
        "ordens_producao_itens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("ordem_id", sa.Integer(), sa.ForeignKey("ordens_producao.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("tipo_abastecimento", PgEnum(name="tipoabastecimento", create_type=False), nullable=False),
        sa.Column("unidade", PgEnum(name="unidademedida", create_type=False), nullable=False),
        sa.Column("quantidade_produzida", sa.Numeric(12, 3), nullable=True),
        sa.UniqueConstraint("negocio_id", "id", name="uq_ordem_item_negocio_id"),
        sa.UniqueConstraint("ordem_id", "produto_id", name="uq_ordem_item_produto"),
        sa.CheckConstraint("quantidade_produzida IS NULL OR quantidade_produzida >= 0",
                           name="ck_ordem_item_produzida_nao_negativa"),
        sa.ForeignKeyConstraint(
            ["negocio_id", "ordem_id"], ["ordens_producao.negocio_id", "ordens_producao.id"],
            name="fk_ordem_item_negocio_ordem", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
            name="fk_ordem_item_negocio_produto",
        ),
    )

    op.create_table(
        "ordens_producao_linhas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("ordens_producao_itens.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("quantidade_sugerida", sa.Numeric(12, 3), nullable=True),
        sa.Column("quantidade_final", sa.Numeric(12, 3), nullable=True),
        sa.Column("componentes", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("avisos", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("editado_em", sa.DateTime(), nullable=True),
        sa.Column("editado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("motivo_edicao", sa.String(length=255), nullable=True),
        sa.Column("quantidade_recebida", sa.Numeric(12, 3), nullable=True),
        sa.Column("recebido_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("item_id", "loja_id", name="uq_ordem_linha_item_loja"),
        sa.CheckConstraint("quantidade_sugerida IS NULL OR quantidade_sugerida >= 0",
                           name="ck_ordem_linha_sugerida_nao_negativa"),
        sa.CheckConstraint("quantidade_final IS NULL OR quantidade_final >= 0",
                           name="ck_ordem_linha_final_nao_negativa"),
        sa.CheckConstraint("quantidade_recebida IS NULL OR quantidade_recebida >= 0",
                           name="ck_ordem_linha_recebida_nao_negativa"),
        sa.ForeignKeyConstraint(
            ["negocio_id", "item_id"], ["ordens_producao_itens.negocio_id", "ordens_producao_itens.id"],
            name="fk_ordem_linha_negocio_item", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_ordem_linha_negocio_loja",
        ),
    )
    # Trânsito (D43) e "linhas da loja": busca por loja.
    op.create_index("ix_ordem_linhas_loja", "ordens_producao_linhas", ["negocio_id", "loja_id"])


def downgrade() -> None:
    op.drop_index("ix_ordem_linhas_loja", table_name="ordens_producao_linhas")
    op.drop_table("ordens_producao_linhas")
    op.drop_table("ordens_producao_itens")
    op.drop_index("uq_ordem_programada_central_data", table_name="ordens_producao")
    op.drop_index("ix_ordens_central_data", table_name="ordens_producao")
    op.drop_table("ordens_producao")
    for enum_ in (tipo_enum, status_enum):
        enum_.drop(op.get_bind(), checkfirst=True)
