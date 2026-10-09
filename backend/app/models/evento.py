"""
Modelos das tabelas `eventos`, `eventos_lojas` e `eventos_produtos`.

Um evento representa um período de demanda atípica (ex.: festa junina,
Natal, feriado local) que ajusta a previsão de produção do negócio.

O ajuste pode se aplicar a todas as lojas ou a um subconjunto específico
(controlado por `escopo_loja`), e a todos os produtos ou a um subconjunto
específico (`escopo_produto`). Quando o escopo é "especificas" ou
"especificos", as tabelas de associação `eventos_lojas` e
`eventos_produtos` indicam quais lojas/produtos participam.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EscopoLoja(str, enum.Enum):
    TODAS = "todas"
    ESPECIFICAS = "especificas"


class EscopoProduto(str, enum.Enum):
    TODOS = "todos"
    ESPECIFICOS = "especificos"


class TipoAjuste(str, enum.Enum):
    MULTIPLICADOR = "multiplicador"
    VALOR_FIXO = "valor_fixo"


class Evento(Base):
    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim: Mapped[date] = mapped_column(Date, nullable=False)

    # values_callable garante uso dos valores string do enum no PostgreSQL.
    escopo_loja: Mapped[EscopoLoja] = mapped_column(
        Enum(EscopoLoja, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )

    escopo_produto: Mapped[EscopoProduto] = mapped_column(
        Enum(EscopoProduto, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )

    tipo_ajuste: Mapped[TipoAjuste] = mapped_column(
        Enum(TipoAjuste, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )

    # Multiplicador (ex.: 3.0 = triplicar a previsão) ou valor fixo de
    # produção para o período, dependendo de `tipo_ajuste`.
    valor_ajuste = mapped_column(Numeric(10, 4), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EventoLoja(Base):
    """Associação evento ↔ loja (usado quando escopo_loja = 'especificas')."""

    __tablename__ = "eventos_lojas"

    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), primary_key=True)


class EventoProduto(Base):
    """Associação evento ↔ produto (usado quando escopo_produto = 'especificos')."""

    __tablename__ = "eventos_produtos"

    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), primary_key=True)
