"""adiciona peso_informado_kg em estoque_atual e historico_contagens

ID da revisão: 0005
Revisa: 0004
Criada em: 2026-07-06

Suporte ao 3º cenário de cálculo de estoque: produtos em KG que NÃO têm
peso médio cadastrado (ex.: bolo vendido por fatia, cujo peso varia a
cada unidade). Nesse caso o responsável pela contagem pesa o item na hora
e o peso informado passa a ser o próprio valor do estoque calculado.

Resumo dos 3 cenários (ver app/services/estoque_service.py):
    UN                          -> estoque_atual_calculado = quantidade_inventariada
    KG com peso_medio_kg        -> estoque_atual_calculado = quantidade_inventariada * peso_medio_kg
    KG sem peso_medio_kg        -> estoque_atual_calculado = peso_informado_kg

`peso_informado_kg` é NULL nos dois primeiros cenários — só é preenchido
quando o produto é KG sem peso médio. Guardado tanto no estado atual
(`estoque_atual`) quanto no snapshot diário (`historico_contagens`), para
manter rastreabilidade uniforme do peso lançado em cada contagem.

Esta migração NÃO é destrutiva — apenas adiciona colunas novas, nullable,
sem afetar dados existentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "estoque_atual",
        sa.Column("peso_informado_kg", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "historico_contagens",
        sa.Column("peso_informado_kg", sa.Numeric(10, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("historico_contagens", "peso_informado_kg")
    op.drop_column("estoque_atual", "peso_informado_kg")
