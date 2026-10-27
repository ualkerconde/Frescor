"""
Modelo da tabela `romaneios` (Fase 5 / E1, doc §3.10; migration 0024).

O romaneio diz quanto de cada produto vai para cada loja, a partir da
ordem de produção aprovada (D68: um romaneio por ordem). Existe à parte da
ordem porque a produção real pode ficar abaixo do planejado (doc §4.8): o
romaneio guarda o rateio sugerido e a decisão do gestor, sem reescrever a
ordem aprovada (D73).

Fluxo (D71): `rascunho` (editável; gerar de novo substitui) → `aprovado`
(travado; imprime e libera o registro da saída). A situação de cada loja
(aguardando saída, expedida, recebida) fica em `romaneios_entregas`.

`central_producao_id` e `data_entrega` repetem os da ordem para facilitar
as consultas por central e dia; a FK composta `fk_romaneio_ordem_coerente`
garante que batem com a ordem. A ordem com romaneio não pode ser apagada.

Isolamento (D2): FK composta com a ordem do mesmo negócio.
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StatusRomaneio(str, enum.Enum):
    RASCUNHO = "rascunho"
    APROVADO = "aprovado"


class Romaneio(Base):
    __tablename__ = "romaneios"
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_romaneio_negocio_id"),
        UniqueConstraint("ordem_id", name="uq_romaneio_ordem"),
        CheckConstraint(
            "(status = 'aprovado' AND aprovado_em IS NOT NULL AND aprovado_por_usuario_id IS NOT NULL)"
            " OR (status = 'rascunho' AND aprovado_em IS NULL AND aprovado_por_usuario_id IS NULL)",
            name="ck_romaneio_aprovacao_coerente",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "central_producao_id", "ordem_id", "data_entrega"],
            ["ordens_producao.negocio_id", "ordens_producao.central_producao_id", "ordens_producao.id",
             "ordens_producao.data_entrega"],
            name="fk_romaneio_ordem_coerente",
        ),
        Index("ix_romaneios_central_entrega", "negocio_id", "central_producao_id", "data_entrega"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    central_producao_id: Mapped[int] = mapped_column(ForeignKey("centrais_producao.id"), nullable=False)
    ordem_id: Mapped[int] = mapped_column(ForeignKey("ordens_producao.id"), nullable=False)
    data_entrega: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatusRomaneio] = mapped_column(
        Enum(StatusRomaneio, name="statusromaneio", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False, default=StatusRomaneio.RASCUNHO, server_default=StatusRomaneio.RASCUNHO.value,
    )
    # Datas e horas em UTC sem fuso, como na ordem (o serviço preenche).
    gerado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    gerado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aprovado_em = mapped_column(DateTime, nullable=True)
    aprovado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Sem relationship: há duas FKs entre as tabelas (simples e composta),
    # como nas ordens; as consultas filtram pelo id.
