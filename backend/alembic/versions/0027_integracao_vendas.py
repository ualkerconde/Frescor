"""integração de vendas com o sistema do cliente (D108)

ID da revisão: 0027
Revisa: 0026
Criada em: 2026-11-11

A venda diária por produto passa a vir do sistema do cliente (ERP/PDV),
sem CSV no dia a dia (D107, D108). O sistema do cliente ainda não foi
definido, então o conector é genérico:
- modo `envio` (push): o sistema do cliente manda as vendas para
  POST /integracao/vendas com uma chave do negócio (guardada só o hash);
- modo `busca` (pull): o Frescor busca de madrugada num endereço do
  cliente que responde no formato do Frescor. A credencial NÃO fica no
  banco: fica numa variável de ambiente do servidor, cujo nome fica aqui.

Tabelas novas:
- `integracoes_vendas`: uma por negócio (modo, endereço, horário, chave).
- `execucoes_sync_vendas`: cada busca ou envio, com o resultado.
- `pendencias_sync_vendas`: linhas que não casaram (loja ou produto
  desconhecido), guardadas para reaplicar quando o produto for casado.
Coluna nova `produtos.codigo_pdv` (nullable): o código do produto no
sistema do cliente, quando é diferente do `codigo`. Única por negócio.

Nada muda no que o app usa (`/produtos` não expõe a coluna nova).
Downgrade: apaga as tabelas, os enums e a coluna.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODOS = ("envio", "busca")
ORIGENS = ("agendada", "manual", "envio")
SITUACOES = ("sucesso", "parcial", "falhou")
MOTIVOS = ("loja_desconhecida", "produto_desconhecido")


def upgrade() -> None:
    bind = op.get_bind()
    modo = postgresql.ENUM(*MODOS, name="modointegracaovendas", create_type=False)
    origem = postgresql.ENUM(*ORIGENS, name="origemexecucaosync", create_type=False)
    situacao = postgresql.ENUM(*SITUACOES, name="situacaoexecucaosync", create_type=False)
    motivo = postgresql.ENUM(*MOTIVOS, name="motivopendenciasync", create_type=False)
    for e in (modo, origem, situacao, motivo):
        e.create(bind, checkfirst=True)

    op.add_column("produtos", sa.Column("codigo_pdv", sa.String(60), nullable=True))
    op.create_index("uq_produto_negocio_codigo_pdv", "produtos", ["negocio_id", "codigo_pdv"], unique=True,
                    postgresql_where=sa.text("codigo_pdv IS NOT NULL"))

    op.create_table(
        "integracoes_vendas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("modo", modo, nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sistema", sa.String(60), nullable=True),
        sa.Column("url_busca", sa.String(500), nullable=True),
        sa.Column("variavel_credencial", sa.String(100), nullable=True),
        sa.Column("horario_busca", sa.Time(), nullable=False, server_default=sa.text("'05:00'")),
        sa.Column("dias_rebusca", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("chave_hash", sa.String(64), nullable=True),
        sa.Column("chave_prefixo", sa.String(12), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("negocio_id", name="uq_integracao_vendas_negocio"),
        sa.UniqueConstraint("chave_hash", name="uq_integracao_vendas_chave"),
        sa.CheckConstraint("dias_rebusca BETWEEN 0 AND 14", name="ck_integracao_vendas_dias_rebusca"),
        sa.CheckConstraint("modo <> 'busca' OR url_busca IS NOT NULL", name="ck_integracao_vendas_busca_tem_url"),
        sa.CheckConstraint("modo <> 'envio' OR chave_hash IS NOT NULL", name="ck_integracao_vendas_envio_tem_chave"),
    )

    op.create_table(
        "execucoes_sync_vendas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("origem", origem, nullable=False),
        sa.Column("situacao", situacao, nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(), nullable=False),
        sa.Column("terminada_em", sa.DateTime(), nullable=True),
        sa.Column("linhas_recebidas", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("linhas_gravadas", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("linhas_pendentes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("linhas_invalidas", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mensagem", sa.String(500), nullable=True),
        sa.Column("iniciada_por_usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
    )
    op.create_index("ix_execucoes_sync_vendas_negocio_iniciada", "execucoes_sync_vendas",
                    ["negocio_id", "iniciada_em"])

    op.create_table(
        "pendencias_sync_vendas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocios.id"), nullable=False),
        sa.Column("motivo", motivo, nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("codigo_loja", sa.String(60), nullable=False),
        sa.Column("codigo_produto", sa.String(60), nullable=False),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.Column("execucao_id", sa.Integer(), sa.ForeignKey("execucoes_sync_vendas.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("atualizada_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("negocio_id", "data", "codigo_loja", "codigo_produto",
                            name="uq_pendencia_sync_negocio_data_loja_produto"),
    )
    op.create_index("ix_pendencias_sync_vendas_negocio_produto", "pendencias_sync_vendas",
                    ["negocio_id", "codigo_produto"])


def downgrade() -> None:
    op.drop_index("ix_pendencias_sync_vendas_negocio_produto", table_name="pendencias_sync_vendas")
    op.drop_table("pendencias_sync_vendas")
    op.drop_index("ix_execucoes_sync_vendas_negocio_iniciada", table_name="execucoes_sync_vendas")
    op.drop_table("execucoes_sync_vendas")
    op.drop_table("integracoes_vendas")
    op.drop_index("uq_produto_negocio_codigo_pdv", table_name="produtos")
    op.drop_column("produtos", "codigo_pdv")
    bind = op.get_bind()
    for nome in ("motivopendenciasync", "situacaoexecucaosync", "origemexecucaosync", "modointegracaovendas"):
        postgresql.ENUM(name=nome).drop(bind, checkfirst=True)
