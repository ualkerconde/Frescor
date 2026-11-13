"""hora da contagem guardada no estoque e no histórico (D111)

ID da revisão: 0028
Revisa: 0027
Criada em: 2026-11-11

A perda sem registro (D111) compara a contagem do fechamento de ontem com a
de hoje. Para saber se um snapshot do histórico é uma contagem de verdade
daquele dia (e não o valor velho que ficou porque a loja não contou), é
preciso a hora em que a contagem foi lançada. `estoque_atual.atualizado_em`
não serve: a zeragem também mexe na linha (zera o rascunho) e muda essa
hora.

Colunas novas, as duas nullable (o app em produção não é afetado; nenhum
endpoint do app passa a devolver ou exigir o campo):
- `estoque_atual.contado_em`: hora (UTC) do último lançamento de contagem
  do app; só o lançamento muda (a zeragem não).
- `historico_contagens.contado_em`: cópia dela no momento do snapshot.

Contagens de antes desta migration ficam sem hora: para esses dias a perda
sem registro não é calculada.

Downgrade: remove as duas colunas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("estoque_atual", sa.Column("contado_em", sa.DateTime(), nullable=True))
    op.add_column("historico_contagens", sa.Column("contado_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("historico_contagens", "contado_em")
    op.drop_column("estoque_atual", "contado_em")
