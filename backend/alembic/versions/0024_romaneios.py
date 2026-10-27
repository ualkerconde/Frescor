"""romaneios: romaneio da ordem aprovada, entrega por loja e itens; produção real

ID da revisão: 0024
Revisa: 0023
Criada em: 2026-10-27

Fase 5 / E1 (doc §3.10, §3.11, §4.8; decisões D68, D69, D71, D74–D78).

- `romaneios`: um por ordem programada aprovada (D68; única por ordem).
  Guarda a central e a data de entrega da ordem; uma FK composta com
  (negócio, central, ordem, data de entrega) garante que as duas batem com
  a ordem. Situação `rascunho` (editável, regerável) ou `aprovado` (travado;
  imprime e permite registrar a saída), com quem/quando gerou e aprovou
  (aprovado exige os dois; rascunho não tem nenhum). A ordem com romaneio
  não pode ser apagada (FK sem CASCADE): o romaneio é o que foi mandado.
- `romaneios_entregas`: uma por loja no romaneio (sem rota, D74). Situação
  `aguardando_saida` → `expedida` (saída registrada pela central, D76) →
  `recebida` (confirmada pela loja no app, D77), com quem e quando de cada
  passo; o banco confere que cada situação tem exatamente os campos dela.
  "Sem confirmação" (D79) NÃO é situação gravada: é `expedida` depois do
  fim do dia de entrega, calculado na leitura.
- `romaneios_itens`: um por produto na entrega, ligado à linha da ordem de
  onde veio (uma vez só). Sugerida (do rateio, D70), final (do gestor, D71;
  é a quantidade expedida), recebida (da loja) e o motivo da divergência
  (D78: falta, avaria, a mais, outro). Recebida diferente da final exige
  motivo; motivo sem recebida é recusado.
- `ordens_producao_itens`: `producao_registrada_em` e
  `producao_registrada_por_usuario_id` (D69); a quantidade já existia
  (`quantidade_produzida`). Os três são preenchidos juntos ou nenhum. O
  downgrade mantém a quantidade (que é anterior à 0024); no upgrade
  seguinte, quem/quando desses itens vêm da aprovação da ordem.

Para as FKs compostas novas, a 0024 cria as únicas-alvo
`uq_ordem_negocio_central_id_entrega` em `ordens_producao` e
`uq_ordem_linha_negocio_id` em `ordens_producao_linhas` (o `id` já é único;
só acrescenta índices). Nenhuma tabela do app mobile muda.

Apagar o romaneio apaga entregas e itens (CASCADE): é assim que o rascunho
será regerado (E4).

Downgrade: remove as três tabelas, os três enums, as colunas e constraints
novas de `ordens_producao_itens` e as duas únicas-alvo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

status_enum = sa.Enum("rascunho", "aprovado", name="statusromaneio")
situacao_enum = sa.Enum("aguardando_saida", "expedida", "recebida", name="situacaoentregaromaneio")
motivo_enum = sa.Enum("falta", "avaria", "a_mais", "outro", name="motivodivergenciarecebimento")


def upgrade() -> None:
    for enum_ in (status_enum, situacao_enum, motivo_enum):
        enum_.create(op.get_bind(), checkfirst=True)

    # Únicas-alvo das FKs compostas novas.
    op.create_unique_constraint(
        "uq_ordem_negocio_central_id_entrega", "ordens_producao",
        ["negocio_id", "central_producao_id", "id", "data_entrega"],
    )
    op.create_unique_constraint("uq_ordem_linha_negocio_id", "ordens_producao_linhas", ["negocio_id", "id"])

    # Produção real (D69).
    op.add_column("ordens_producao_itens", sa.Column("producao_registrada_em", sa.DateTime(), nullable=True))
    op.add_column("ordens_producao_itens", sa.Column(
        "producao_registrada_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True))
    # Item que já tem quantidade produzida (só acontece depois de um downgrade
    # da 0024, que apaga quem/quando e mantém a quantidade): quem/quando passam
    # a ser os da aprovação da ordem, para a regra abaixo valer sem perder dado.
    op.execute(
        "UPDATE ordens_producao_itens i"
        " SET producao_registrada_em = coalesce(o.aprovado_em, o.gerado_em),"
        " producao_registrada_por_usuario_id = coalesce(o.aprovado_por_usuario_id, o.gerado_por_usuario_id)"
        " FROM ordens_producao o"
        " WHERE o.id = i.ordem_id AND i.quantidade_produzida IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_ordem_item_producao_coerente", "ordens_producao_itens",
        "(quantidade_produzida IS NULL AND producao_registrada_em IS NULL"
        " AND producao_registrada_por_usuario_id IS NULL)"
        " OR (quantidade_produzida IS NOT NULL AND producao_registrada_em IS NOT NULL"
        " AND producao_registrada_por_usuario_id IS NOT NULL)",
    )

    op.create_table(
        "romaneios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("central_producao_id", sa.Integer(), sa.ForeignKey("centrais_producao.id"), nullable=False),
        sa.Column("ordem_id", sa.Integer(), sa.ForeignKey("ordens_producao.id"), nullable=False),
        sa.Column("data_entrega", sa.Date(), nullable=False),
        sa.Column("status", PgEnum(name="statusromaneio", create_type=False), nullable=False,
                  server_default="rascunho"),
        sa.Column("gerado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("gerado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("aprovado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.UniqueConstraint("negocio_id", "id", name="uq_romaneio_negocio_id"),
        sa.UniqueConstraint("ordem_id", name="uq_romaneio_ordem"),
        sa.CheckConstraint(
            "(status = 'aprovado' AND aprovado_em IS NOT NULL AND aprovado_por_usuario_id IS NOT NULL)"
            " OR (status = 'rascunho' AND aprovado_em IS NULL AND aprovado_por_usuario_id IS NULL)",
            name="ck_romaneio_aprovacao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "central_producao_id", "ordem_id", "data_entrega"],
            ["ordens_producao.negocio_id", "ordens_producao.central_producao_id", "ordens_producao.id",
             "ordens_producao.data_entrega"],
            name="fk_romaneio_ordem_coerente",
        ),
    )
    op.create_index("ix_romaneios_central_entrega", "romaneios", ["negocio_id", "central_producao_id", "data_entrega"])

    op.create_table(
        "romaneios_entregas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("romaneio_id", sa.Integer(), sa.ForeignKey("romaneios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("situacao", PgEnum(name="situacaoentregaromaneio", create_type=False), nullable=False,
                  server_default="aguardando_saida"),
        sa.Column("expedido_em", sa.DateTime(), nullable=True),
        sa.Column("expedido_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("recebido_em", sa.DateTime(), nullable=True),
        sa.Column("recebido_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("observacao", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("negocio_id", "id", name="uq_entrega_negocio_id"),
        sa.UniqueConstraint("romaneio_id", "loja_id", name="uq_entrega_romaneio_loja"),
        sa.CheckConstraint(
            "(situacao = 'aguardando_saida' AND expedido_em IS NULL AND expedido_por_usuario_id IS NULL"
            " AND recebido_em IS NULL AND recebido_por_usuario_id IS NULL)"
            " OR (situacao = 'expedida' AND expedido_em IS NOT NULL AND expedido_por_usuario_id IS NOT NULL"
            " AND recebido_em IS NULL AND recebido_por_usuario_id IS NULL)"
            " OR (situacao = 'recebida' AND expedido_em IS NOT NULL AND expedido_por_usuario_id IS NOT NULL"
            " AND recebido_em IS NOT NULL AND recebido_por_usuario_id IS NOT NULL)",
            name="ck_entrega_situacao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "romaneio_id"], ["romaneios.negocio_id", "romaneios.id"],
            name="fk_entrega_negocio_romaneio", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_entrega_negocio_loja",
        ),
    )
    # App mobile (D77): entregas da loja por situação.
    op.create_index("ix_entregas_loja_situacao", "romaneios_entregas", ["negocio_id", "loja_id", "situacao"])

    op.create_table(
        "romaneios_itens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("entrega_id", sa.Integer(), sa.ForeignKey("romaneios_entregas.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("produto_id", sa.Integer(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("ordem_linha_id", sa.Integer(), sa.ForeignKey("ordens_producao_linhas.id"), nullable=False),
        sa.Column("unidade", PgEnum(name="unidademedida", create_type=False), nullable=False),
        sa.Column("quantidade_sugerida", sa.Numeric(12, 3), nullable=False),
        sa.Column("quantidade_final", sa.Numeric(12, 3), nullable=False),
        sa.Column("quantidade_recebida", sa.Numeric(12, 3), nullable=True),
        sa.Column("motivo_divergencia", PgEnum(name="motivodivergenciarecebimento", create_type=False),
                  nullable=True),
        sa.Column("observacao_divergencia", sa.String(length=255), nullable=True),
        sa.Column("editado_em", sa.DateTime(), nullable=True),
        sa.Column("editado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("motivo_edicao", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("entrega_id", "produto_id", name="uq_romaneio_item_entrega_produto"),
        sa.UniqueConstraint("ordem_linha_id", name="uq_romaneio_item_ordem_linha"),
        sa.CheckConstraint("quantidade_sugerida >= 0", name="ck_romaneio_item_sugerida_nao_negativa"),
        sa.CheckConstraint("quantidade_final >= 0", name="ck_romaneio_item_final_nao_negativa"),
        sa.CheckConstraint("quantidade_recebida IS NULL OR quantidade_recebida >= 0",
                           name="ck_romaneio_item_recebida_nao_negativa"),
        sa.CheckConstraint(
            "(quantidade_recebida IS NULL AND motivo_divergencia IS NULL)"
            " OR (quantidade_recebida IS NOT NULL"
            " AND (quantidade_recebida = quantidade_final OR motivo_divergencia IS NOT NULL))",
            name="ck_romaneio_item_divergencia_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "entrega_id"], ["romaneios_entregas.negocio_id", "romaneios_entregas.id"],
            name="fk_romaneio_item_negocio_entrega", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
            name="fk_romaneio_item_negocio_produto",
        ),
        sa.ForeignKeyConstraint(
            ["negocio_id", "ordem_linha_id"], ["ordens_producao_linhas.negocio_id", "ordens_producao_linhas.id"],
            name="fk_romaneio_item_negocio_linha",
        ),
    )


def downgrade() -> None:
    op.drop_table("romaneios_itens")
    op.drop_index("ix_entregas_loja_situacao", table_name="romaneios_entregas")
    op.drop_table("romaneios_entregas")
    op.drop_index("ix_romaneios_central_entrega", table_name="romaneios")
    op.drop_table("romaneios")
    op.drop_constraint("ck_ordem_item_producao_coerente", "ordens_producao_itens", type_="check")
    op.drop_column("ordens_producao_itens", "producao_registrada_por_usuario_id")
    op.drop_column("ordens_producao_itens", "producao_registrada_em")
    op.drop_constraint("uq_ordem_linha_negocio_id", "ordens_producao_linhas", type_="unique")
    op.drop_constraint("uq_ordem_negocio_central_id_entrega", "ordens_producao", type_="unique")
    for enum_ in (motivo_enum, situacao_enum, status_enum):
        enum_.drop(op.get_bind(), checkfirst=True)
