"""
Modelo da tabela `pendencias_sync_vendas` (D108, migration 0027).

Por que existe: o sistema do cliente manda a venda com os códigos DELE
(loja e produto). O que não casa com uma loja (`lojas.codigo`) ou com um
produto (`produtos.codigo_pdv`, ou o `codigo` quando não há código no PDV)
não pode travar o resto: a linha fica guardada aqui, com a quantidade, e o
gestor vê a lista. Quando ele diz qual produto é aquele código, as linhas
guardadas são gravadas na hora, sem esperar a próxima busca.

Uma linha por negócio + dia + loja + produto (o envio seguinte substitui).
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MotivoPendenciaSync(str, enum.Enum):
    LOJA_DESCONHECIDA = "loja_desconhecida"
    PRODUTO_DESCONHECIDO = "produto_desconhecido"


class PendenciaSyncVendas(Base):
    __tablename__ = "pendencias_sync_vendas"
    __table_args__ = (
        UniqueConstraint("negocio_id", "data", "codigo_loja", "codigo_produto",
                         name="uq_pendencia_sync_negocio_data_loja_produto"),
        Index("ix_pendencias_sync_vendas_negocio_produto", "negocio_id", "codigo_produto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    motivo: Mapped[MotivoPendenciaSync] = mapped_column(
        Enum(MotivoPendenciaSync, name="motivopendenciasync",
             values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    codigo_loja: Mapped[str] = mapped_column(String(60), nullable=False)
    codigo_produto: Mapped[str] = mapped_column(String(60), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    execucao_id = mapped_column(ForeignKey("execucoes_sync_vendas.id", ondelete="SET NULL"), nullable=True)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
