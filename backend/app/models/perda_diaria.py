"""
Modelo da tabela `perdas_diarias`.

Quanto de cada produto cada loja perdeu (validade vencida, quebra, descarte)
em cada dia. Junto com a venda, mostra se a produção está sobrando: perda
alta e recorrente é sinal de que a necessidade calculada está acima do
que a loja consegue vender.

Mesmas regras de `vendas_diarias` (D2, D5, D6 em docs/STATUS.md), com uma
origem a mais:
- `inferida`: perda calculada pelo sistema a partir do cruzamento entre o
  estoque esperado e o estoque contado (doc de referência §4.6). Só é
  gerada na Fase 8; o valor já existe no enum para não exigir migração de
  enum depois.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrigemPerda(str, enum.Enum):
    API = "api"
    MANUAL = "manual"
    INFERIDA = "inferida"


class PerdaDiaria(Base):
    __tablename__ = "perdas_diarias"
    __table_args__ = (
        UniqueConstraint("loja_id", "produto_id", "data", "origem", name="uq_perda_loja_produto_data_origem"),
        CheckConstraint("quantidade >= 0", name="ck_perda_quantidade_nao_negativa"),
        # Loja e produto têm de ser do mesmo negócio da linha (D2, garantido
        # no banco, além da validação do serviço de importação).
        ForeignKeyConstraint(["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_perda_negocio_loja"),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_perda_negocio_produto"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    origem: Mapped[OrigemPerda] = mapped_column(
        Enum(OrigemPerda, name="origemperda", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Muda quando uma reimportação substitui a quantidade (D5).
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
