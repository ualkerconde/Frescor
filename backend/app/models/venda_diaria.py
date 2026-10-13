"""
Modelo da tabela `vendas_diarias`.

Quanto de cada produto cada loja vendeu em cada dia. É a matéria-prima do
motor de previsão (Fase 3): sem histórico de venda não há previsão, e sem
previsão não há necessidade nem ordem de produção.

Enquanto a integração com o PDV da rede não existe (decisão D3 em aberto),
os dados chegam por importação de CSV (`origem = manual`). Quando a
integração existir, chegam por `sync_vendas_service` (`origem = api`). As
duas origens do mesmo dia podem coexistir, o que permite comparar o
manual com o automático na transição.

Regras (docs/STATUS.md):
- D2: `negocio_id` redundante (a loja e o produto já pertencem a um
  negócio), de propósito, para toda consulta filtrar direto por negócio.
- D5: uma linha por loja + produto + data + origem (uq). Reimportar o
  mesmo dia da mesma origem substitui a quantidade.
- D6: `quantidade` na unidade do produto (UN -> peças, KG -> kg), com até
  3 casas decimais, nunca negativa.
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


class OrigemVenda(str, enum.Enum):
    API = "api"
    MANUAL = "manual"


class VendaDiaria(Base):
    __tablename__ = "vendas_diarias"
    __table_args__ = (
        UniqueConstraint("loja_id", "produto_id", "data", "origem", name="uq_venda_loja_produto_data_origem"),
        CheckConstraint("quantidade >= 0", name="ck_venda_quantidade_nao_negativa"),
        # Loja e produto têm de ser do mesmo negócio da linha (D2, garantido
        # no banco, além da validação do serviço de importação).
        ForeignKeyConstraint(["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_venda_negocio_loja"),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_venda_negocio_produto"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    origem: Mapped[OrigemVenda] = mapped_column(
        Enum(OrigemVenda, name="origemvenda", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Muda quando uma reimportação substitui a quantidade (D5).
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
