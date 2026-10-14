"""
Modelos das tabelas `eventos`, `eventos_lojas` e `eventos_produtos`.

Um evento representa um período de demanda atípica (ex.: festa junina,
Natal, feriado local) que ajusta a previsão de venda (doc §4.3). Os dias
cobertos por um evento também ficam fora da base da previsão dos dias
normais seguintes.

Cada evento pertence a uma central de produção (D27): é a unidade em que
o gestor trabalha, e "todas as lojas" (`escopo_loja = todas`) significa
todas as lojas DA CENTRAL do evento, nunca as de outra central. Com
`escopo_loja = especificas`, `eventos_lojas` lista as lojas. O mesmo vale
para produtos: `escopo_produto = todos`, ou `eventos_produtos` lista os
produtos.

`central_producao_id` é nullable só por compatibilidade (coluna nova em
tabela existente, migration 0018): todo evento criado pela API tem central.
Um evento antigo sem central e com "todas as lojas" vale para todas as
lojas do negócio.

Isolamento (D2): as tabelas de associação têm `negocio_id` e FKs compostas
para o evento, a loja e o produto do MESMO negócio. O banco recusa ligar
um evento a uma loja ou produto de outro negócio, além da validação do
serviço.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint
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
    __table_args__ = (
        # Alvo das FKs compostas das tabelas de associação.
        UniqueConstraint("negocio_id", "id", name="uq_evento_negocio_id"),
        ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"],
            ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_evento_negocio_central",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Central do evento (D27). Nullable só por compatibilidade, ver docstring.
    central_producao_id = mapped_column(ForeignKey("centrais_producao.id"), nullable=True, index=True)

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

    # Decisão D26 (docs/STATUS.md), em cada dia do evento:
    # - multiplicador: multiplica a previsão do dia (ex.: 1.5 = +50%);
    #   vários multiplicadores no mesmo dia se multiplicam;
    # - valor_fixo: é a previsão DIÁRIA de cada loja + produto do escopo
    #   (não um total do período); substitui a previsão normal e vence
    #   qualquer multiplicador; entre dois valores fixos, vale o último
    #   cadastrado.
    valor_ajuste = mapped_column(Numeric(10, 4), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EventoLoja(Base):
    """Associação evento ↔ loja (usado quando escopo_loja = 'especificas')."""

    __tablename__ = "eventos_lojas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["negocio_id", "evento_id"], ["eventos.negocio_id", "eventos.id"], name="fk_evento_loja_negocio_evento"
        ),
        ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_evento_loja_negocio_loja"
        ),
    )

    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), primary_key=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)


class EventoProduto(Base):
    """Associação evento ↔ produto (usado quando escopo_produto = 'especificos')."""

    __tablename__ = "eventos_produtos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["negocio_id", "evento_id"], ["eventos.negocio_id", "eventos.id"], name="fk_evento_produto_negocio_evento"
        ),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_evento_produto_negocio_produto"
        ),
    )

    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), primary_key=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
