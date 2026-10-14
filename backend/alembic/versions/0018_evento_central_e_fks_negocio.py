"""evento por central (D27) e FKs compostas por negócio nas associações

ID da revisão: 0018
Revisa: 0017
Criada em: 2026-10-13

D27: cada evento passa a pertencer a uma central de produção, para que
"todas as lojas" signifique todas as lojas DA CENTRAL do evento (antes
valeria para as lojas de todas as centrais do negócio).

Isolamento (D2): `eventos_lojas` e `eventos_produtos` ganham `negocio_id`
e FKs compostas para o evento, a loja e o produto do mesmo negócio. Antes,
o banco aceitava ligar um evento a uma loja de outro negócio (só o serviço
impedia).

Upgrade:
1. UNIQUE (negocio_id, id) em `centrais_producao` e em `eventos` (alvos
   das FKs compostas; `lojas` e `produtos` já têm).
2. `eventos.central_producao_id` (nullable, com FK simples e FK composta
   com o negócio). Preenchimento das linhas existentes: evento de lojas
   específicas que são todas da mesma central -> essa central; evento de
   "todas as lojas" num negócio com uma central só -> essa central. O
   resto fica NULL (evento antigo: "todas" vale para o negócio inteiro).
3. `negocio_id` nas associações, preenchido a partir do evento, NOT NULL,
   com as FKs compostas. Se alguma associação antiga ligar um evento a
   loja/produto de outro negócio, a FK composta falha e a migração para
   (o dado está inconsistente e precisa ser corrigido à mão). Em
   2026-10-13 as três tabelas estavam vazias no banco de desenvolvimento.

`negocio_id` NOT NULL nas associações, apesar da regra de colunas novas
nullable: com NULL, a FK composta não é verificada pelo PostgreSQL (MATCH
SIMPLE), o que anularia o objetivo. Nenhuma versão anterior do app grava
nessas tabelas (o cadastro de eventos nasceu no mesmo passo, F3).

Downgrade: remove as FKs, as colunas e as constraints únicas, nessa ordem.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_central_negocio_id", "centrais_producao", ["negocio_id", "id"])
    op.create_unique_constraint("uq_evento_negocio_id", "eventos", ["negocio_id", "id"])

    # ---- eventos.central_producao_id ----
    op.add_column("eventos", sa.Column("central_producao_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "eventos_central_producao_id_fkey", "eventos", "centrais_producao", ["central_producao_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_evento_negocio_central", "eventos", "centrais_producao",
        ["negocio_id", "central_producao_id"], ["negocio_id", "id"],
    )
    op.create_index("ix_eventos_central_producao_id", "eventos", ["central_producao_id"])
    op.execute(sa.text("""
        UPDATE eventos e SET central_producao_id = x.central
        FROM (
            SELECT el.evento_id, MIN(l.central_producao_id) AS central
            FROM eventos_lojas el JOIN lojas l ON l.id = el.loja_id
            GROUP BY el.evento_id
            HAVING COUNT(DISTINCT l.central_producao_id) = 1
        ) x
        WHERE e.id = x.evento_id AND e.escopo_loja = 'especificas'
    """))
    op.execute(sa.text("""
        UPDATE eventos e SET central_producao_id = x.central
        FROM (
            SELECT negocio_id, MIN(id) AS central
            FROM centrais_producao
            GROUP BY negocio_id
            HAVING COUNT(*) = 1
        ) x
        WHERE e.negocio_id = x.negocio_id AND e.escopo_loja = 'todas'
    """))

    # ---- negocio_id nas associações ----
    for tabela, coluna, alvo, fk_alvo in (
        ("eventos_lojas", "loja_id", "lojas", "fk_evento_loja_negocio_loja"),
        ("eventos_produtos", "produto_id", "produtos", "fk_evento_produto_negocio_produto"),
    ):
        prefixo = "fk_evento_loja" if tabela == "eventos_lojas" else "fk_evento_produto"
        op.add_column(tabela, sa.Column("negocio_id", sa.Integer(), nullable=True))
        op.execute(sa.text(
            f"UPDATE {tabela} a SET negocio_id = e.negocio_id FROM eventos e WHERE e.id = a.evento_id"
        ))
        op.alter_column(tabela, "negocio_id", nullable=False)
        op.create_foreign_key(f"{tabela}_negocio_id_fkey", tabela, "negocios", ["negocio_id"], ["id"])
        op.create_foreign_key(
            f"{prefixo}_negocio_evento", tabela, "eventos", ["negocio_id", "evento_id"], ["negocio_id", "id"]
        )
        op.create_foreign_key(fk_alvo, tabela, alvo, ["negocio_id", coluna], ["negocio_id", "id"])


def downgrade() -> None:
    for tabela, prefixo, fk_alvo in (
        ("eventos_produtos", "fk_evento_produto", "fk_evento_produto_negocio_produto"),
        ("eventos_lojas", "fk_evento_loja", "fk_evento_loja_negocio_loja"),
    ):
        op.drop_constraint(fk_alvo, tabela, type_="foreignkey")
        op.drop_constraint(f"{prefixo}_negocio_evento", tabela, type_="foreignkey")
        op.drop_constraint(f"{tabela}_negocio_id_fkey", tabela, type_="foreignkey")
        op.drop_column(tabela, "negocio_id")

    op.drop_index("ix_eventos_central_producao_id", table_name="eventos")
    op.drop_constraint("fk_evento_negocio_central", "eventos", type_="foreignkey")
    op.drop_constraint("eventos_central_producao_id_fkey", "eventos", type_="foreignkey")
    op.drop_column("eventos", "central_producao_id")

    op.drop_constraint("uq_evento_negocio_id", "eventos", type_="unique")
    op.drop_constraint("uq_central_negocio_id", "centrais_producao", type_="unique")
