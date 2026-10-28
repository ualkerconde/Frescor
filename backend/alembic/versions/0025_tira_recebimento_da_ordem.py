"""tira o recebimento da linha da ordem (passa a ficar no romaneio)

ID da revisão: 0025
Revisa: 0024
Criada em: 2026-10-28

Fase 5 / E5 (D75, D79). O recebimento da loja fica em `romaneios_entregas`
(quem e quando) e `romaneios_itens` (recebida e motivo). As colunas
`quantidade_recebida` e `recebido_em` de `ordens_producao_linhas`, criadas
na 0022 para a Fase 5 e nunca preenchidas, saem com a regra
`ck_ordem_linha_recebida_nao_negativa`. O trânsito da necessidade passa a
ler o romaneio (`producao_service.provedor_transito_ordens`).

Proteção: se alguma linha tiver algum dos dois preenchido (não deveria:
nenhum código grava neles), o upgrade para sem apagar nada, para não perder
dado em silêncio.

Downgrade: recria as duas colunas (vazias, nullable) e a regra. O que foi
confirmado no romaneio continua lá; o código antigo não o lê.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    preenchidas = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM ordens_producao_linhas"
        " WHERE quantidade_recebida IS NOT NULL OR recebido_em IS NOT NULL"
    )).scalar()
    if preenchidas:
        raise RuntimeError(
            f"{preenchidas} linha(s) de ordem com recebimento gravado: confira antes de apagar as colunas."
        )
    op.drop_constraint("ck_ordem_linha_recebida_nao_negativa", "ordens_producao_linhas", type_="check")
    op.drop_column("ordens_producao_linhas", "recebido_em")
    op.drop_column("ordens_producao_linhas", "quantidade_recebida")


def downgrade() -> None:
    op.add_column("ordens_producao_linhas", sa.Column("quantidade_recebida", sa.Numeric(12, 3), nullable=True))
    op.add_column("ordens_producao_linhas", sa.Column("recebido_em", sa.DateTime(), nullable=True))
    op.create_check_constraint(
        "ck_ordem_linha_recebida_nao_negativa", "ordens_producao_linhas",
        "quantidade_recebida IS NULL OR quantidade_recebida >= 0",
    )
