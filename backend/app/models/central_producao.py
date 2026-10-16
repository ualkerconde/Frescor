"""
Modelo da tabela `centrais_producao`.

Uma central de produção é a unidade fabril/de distribuição da rede que
produz e abastece as lojas. Cada negócio pode ter uma ou mais centrais
(ex.: padaria central e cozinha de salgados), mas toda loja deve estar
vinculada a exatamente uma central de produção.

O gestor da central (tipo_usuario = gestor_central em app/models/usuario.py)
opera neste escopo, não no escopo de loja.

Cada central atende uma seção só (padaria, açougue, hortifruti), com a
mesma lógica (D14). O prazo de entrega diz quantos dias depois da produção
a mercadoria chega à loja (D32): a necessidade cobre os dias a partir da
chegada. Os dois campos vêm da migration 0020.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SecaoCentral(str, enum.Enum):
    PADARIA = "padaria"
    ACOUGUE = "acougue"
    HORTIFRUTI = "hortifruti"


class CentralProducao(Base):
    __tablename__ = "centrais_producao"
    __table_args__ = (
        # Alvo da FK composta de eventos (central do mesmo negócio, D27).
        UniqueConstraint("negocio_id", "id", name="uq_central_negocio_id"),
        CheckConstraint("prazo_entrega_dias >= 0", name="ck_central_prazo_entrega_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    secao: Mapped[SecaoCentral] = mapped_column(
        Enum(SecaoCentral, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=SecaoCentral.PADARIA,
        server_default=SecaoCentral.PADARIA.value,
        nullable=False,
    )

    # Dias entre a produção (D) e a entrega na loja; 0 = entrega no próprio D.
    prazo_entrega_dias: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    negocio = relationship("Negocio", back_populates="centrais_producao")
    lojas = relationship("Loja", back_populates="central_producao")
    usuarios = relationship("Usuario", back_populates="central_producao")
