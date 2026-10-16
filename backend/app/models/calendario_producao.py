"""
Modelo da tabela `calendario_producao`.

Define em quais dias da semana um produto deve ser produzido pela central.
A combinação (produto_id, dia_semana) é única: o mesmo produto não pode
aparecer duas vezes no mesmo dia da semana.

Para produto distribuído (D39), os dias são os de envio pela central.

`negocio_id` (migration 0020): permite filtrar o calendário direto pelo
negócio (regra de ouro 1); a FK composta garante no banco que o produto é
do mesmo negócio.
"""

import enum

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DiaSemana(str, enum.Enum):
    SEGUNDA = "segunda"
    TERCA = "terca"
    QUARTA = "quarta"
    QUINTA = "quinta"
    SEXTA = "sexta"
    SABADO = "sabado"
    DOMINGO = "domingo"


class CalendarioProducao(Base):
    __tablename__ = "calendario_producao"
    __table_args__ = (
        UniqueConstraint("produto_id", "dia_semana", name="uq_calendario_produto_dia"),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
            name="fk_calendario_negocio_produto",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)

    # values_callable força o SQLAlchemy a usar os VALORES do enum Python
    # ("segunda", "terca", ...) e não os NOMES ("SEGUNDA", "TERCA", ...).
    dia_semana: Mapped[DiaSemana] = mapped_column(
        Enum(DiaSemana, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
