"""
Modelo da tabela `ordens_producao` (Fase 4 / N5, doc §3.8; migration 0022).

A ordem do dia de uma central: o que produzir (e distribuir) para as lojas,
calculado pela necessidade (N3/N4) e revisado pelo gestor antes de valer.

Por que existe a situação `rascunho` (D38): o número do sistema é uma
sugestão; o gestor confere, ajusta loja por loja e só então aprova. O
rascunho pode ser regerado (apagar e gerar de novo); a ordem `aprovada`
fica travada, vira o compromisso com as lojas e passa a contar como
estoque em trânsito para as ordens seguintes (D43).

Uma ordem `programada` por central e data de produção (índice único
parcial); `emergencial` é para a checagem intradiária da Fase 8.

`data_entrega` é gravada na geração (D + prazo da central, D32): se o prazo
mudar depois, a ordem antiga continua dizendo quando ela chega.
`versao_metodo` e `referencia_previsao` dizem com qual regra e qual
previsão o número foi calculado (para explicar e comparar depois).

Isolamento (D2): FK composta com a central do mesmo negócio.
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
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StatusOrdemProducao(str, enum.Enum):
    RASCUNHO = "rascunho"
    APROVADA = "aprovada"


class TipoOrdemProducao(str, enum.Enum):
    PROGRAMADA = "programada"
    EMERGENCIAL = "emergencial"  # Fase 8 (doc §4.7)


def _enum(cls, nome):
    return Enum(cls, name=nome, values_callable=lambda enum_cls: [e.value for e in enum_cls])


class OrdemProducao(Base):
    __tablename__ = "ordens_producao"
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_ordem_negocio_id"),
        CheckConstraint("data_entrega >= data_producao", name="ck_ordem_entrega_depois_da_producao"),
        CheckConstraint(
            "(status = 'aprovada' AND aprovado_em IS NOT NULL AND aprovado_por_usuario_id IS NOT NULL)"
            " OR (status = 'rascunho' AND aprovado_em IS NULL AND aprovado_por_usuario_id IS NULL)",
            name="ck_ordem_aprovacao_coerente",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"], ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_ordem_negocio_central",
        ),
        Index("ix_ordens_central_data", "negocio_id", "central_producao_id", "data_producao"),
        Index(
            "uq_ordem_programada_central_data", "central_producao_id", "data_producao",
            unique=True, postgresql_where=text("tipo = 'programada'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    central_producao_id: Mapped[int] = mapped_column(ForeignKey("centrais_producao.id"), nullable=False)
    data_producao: Mapped[date] = mapped_column(Date, nullable=False)
    data_entrega: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoOrdemProducao] = mapped_column(
        _enum(TipoOrdemProducao, "tipoordemproducao"), nullable=False,
        default=TipoOrdemProducao.PROGRAMADA, server_default=TipoOrdemProducao.PROGRAMADA.value,
    )
    status: Mapped[StatusOrdemProducao] = mapped_column(
        _enum(StatusOrdemProducao, "statusordemproducao"), nullable=False,
        default=StatusOrdemProducao.RASCUNHO, server_default=StatusOrdemProducao.RASCUNHO.value,
    )
    versao_metodo: Mapped[str] = mapped_column(String(32), nullable=False)
    # Data de referência mais antiga das previsões usadas (None = nenhuma).
    referencia_previsao = mapped_column(Date, nullable=True)
    gerado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    gerado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aprovado_em = mapped_column(DateTime, nullable=True)
    aprovado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Sem relationship com os itens: há duas FKs entre as tabelas (a simples e
    # a composta com o negócio), o que deixa o join ambíguo para o ORM; as
    # consultas filtram pelo id, como nas outras tabelas com FK composta.
