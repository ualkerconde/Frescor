"""
Modelo da tabela `calendario_producao`.

Define em quais dias da semana um produto deve ser produzido pela central.
A combinação (produto_id, dia_semana) é única: o mesmo produto não pode
aparecer duas vezes no mesmo dia da semana.
"""

import enum

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
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
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)

    # values_callable força o SQLAlchemy a usar os VALORES do enum Python
    # ("segunda", "terca", ...) e não os NOMES ("SEGUNDA", "TERCA", ...).
    dia_semana: Mapped[DiaSemana] = mapped_column(
        Enum(DiaSemana, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
