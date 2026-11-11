"""
Modelo da tabela `lancamentos_perda` (D110, migration 0026).

Por que existe: o supermercado em geral não registra a perda dos itens
produzidos na loja (análise de 07/11/2026), então ela não vem do PDV como a
venda. A loja lança no app, no momento do descarte (produto, quantidade,
motivo), e o gestor vê e corrige no SaaS.

Cada lançamento fica guardado (quem, quando, motivo) para auditoria. A SOMA
dos lançamentos de uma loja + produto + dia é gravada em `perdas_diarias`
com origem `manual` (`perda_lancamento_service.recalcular_perda_do_dia`),
que é de onde previsão, necessidade e consultas já leem a perda. Assim
nenhum consumidor precisou mudar.

Regras (D110): quantidade > 0, na unidade do produto (UN inteira); motivo
de uma lista fixa; a loja corrige o próprio lançamento até o fim de D+1,
depois só o gestor.
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
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MotivoPerda(str, enum.Enum):
    VENCIDO = "vencido"
    AVARIADO = "avariado"
    OUTRO = "outro"


class LancamentoPerda(Base):
    __tablename__ = "lancamentos_perda"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_lancamento_perda_quantidade_positiva"),
        ForeignKeyConstraint(["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"],
                             name="fk_lancamento_perda_negocio_loja"),
        ForeignKeyConstraint(["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
                             name="fk_lancamento_perda_negocio_produto"),
        Index("ix_lancamentos_perda_loja_data", "loja_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    motivo: Mapped[MotivoPerda] = mapped_column(
        Enum(MotivoPerda, name="motivoperda", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    observacao = mapped_column(String(200), nullable=True)
    lancado_por_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    lancado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    alterado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    alterado_em = mapped_column(DateTime, nullable=True)
