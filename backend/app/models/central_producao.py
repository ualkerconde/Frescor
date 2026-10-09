"""
Modelo da tabela `centrais_producao`.

Uma central de produção é a unidade fabril/de distribuição da rede que
produz e abastece as lojas. Cada negócio pode ter uma ou mais centrais
(ex.: padaria central e cozinha de salgados), mas toda loja deve estar
vinculada a exatamente uma central de produção.

O gestor da central (tipo_usuario = gestor_central em app/models/usuario.py)
opera neste escopo, não no escopo de loja.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CentralProducao(Base):
    __tablename__ = "centrais_producao"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    negocio = relationship("Negocio", back_populates="centrais_producao")
    lojas = relationship("Loja", back_populates="central_producao")
    usuarios = relationship("Usuario", back_populates="central_producao")
