"""adiciona central_producao_id em lojas

ID da revisão: 0008
Revisa: 0007
Criada em: 2026-08-20

Vincula cada loja à sua central de produção. Como pode haver lojas
cadastradas antes desta migração, adotamos a seguinte estratégia segura
para dado existente:

  1. Adiciona `central_producao_id` como nullable.
  2. Para cada negócio que tenha ao menos uma loja, cria uma central de
     produção padrão chamada "Central Principal (Padrão)".
  3. Associa todas as lojas existentes daquele negócio a essa central.
  4. Torna a coluna NOT NULL.

Isso garante que `alembic upgrade head` funcione tanto em banco limpo
quanto em banco com dados reais. Em produção, o administrador poderá
depois criar centrais adicionais e reatribuir as lojas pela interface web.

O downgrade remove a coluna (e, opcionalmente, as centrais padrão criadas
automaticamente — aqui apenas a coluna é removida, pois a tabela
`centrais_producao` é gerenciada pela migração 0007).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Passo 1: adiciona a coluna como nullable para permitir o backfill.
    op.add_column(
        "lojas",
        sa.Column("central_producao_id", sa.Integer(), sa.ForeignKey("centrais_producao.id"), nullable=True),
    )
    op.create_index("ix_lojas_central_producao_id", "lojas", ["central_producao_id"])

    # Passo 2 + 3: cria uma central padrão por negócio e associa as lojas.
    conn = op.get_bind()

    # Coleta todos os negocio_id distintos que têm lojas cadastradas.
    result = conn.execute(sa.text("SELECT DISTINCT negocio_id FROM lojas"))
    negocio_ids = [row[0] for row in result]

    for negocio_id in negocio_ids:
        # Insere a central padrão e recupera o id gerado.
        ins = conn.execute(
            sa.text(
                "INSERT INTO centrais_producao (negocio_id, nome, ativa, criado_em) "
                "VALUES (:negocio_id, 'Central Principal (Padrão)', true, NOW()) "
                "RETURNING id"
            ),
            {"negocio_id": negocio_id},
        )
        central_id = ins.fetchone()[0]

        # Associa todas as lojas deste negócio à central recém-criada.
        conn.execute(
            sa.text(
                "UPDATE lojas SET central_producao_id = :central_id "
                "WHERE negocio_id = :negocio_id"
            ),
            {"central_id": central_id, "negocio_id": negocio_id},
        )

    # Passo 4: torna a coluna NOT NULL agora que todas as lojas foram associadas.
    op.alter_column("lojas", "central_producao_id", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_lojas_central_producao_id", table_name="lojas")
    op.drop_column("lojas", "central_producao_id")
