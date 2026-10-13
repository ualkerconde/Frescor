"""
Modelo da tabela `lojas`.

Cada negócio (rede) pode ter múltiplas lojas. A loja é o nível em que a
operação de contagem de estoque realmente acontece: cada usuário do app
pertence a uma loja fixa, e cada loja tem seu próprio horário de zeragem
diária e seu próprio conjunto de produtos habilitados (ver
app/models/produto_loja.py).

`codigo` (opcional, único dentro do negócio, migration 0015): o código com
que a rede identifica a loja nos próprios sistemas. É por ele que a loja é
reconhecida no CSV de importação de vendas e perdas (decisão D7, provisória).
"""

from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Loja(Base):
    __tablename__ = "lojas"
    __table_args__ = (
        UniqueConstraint("negocio_id", "codigo", name="uq_loja_negocio_codigo"),
        # Alvo das FKs compostas de vendas_diarias/perdas_diarias (migration
        # 0015): garante no banco que venda/perda e loja são do mesmo negócio.
        UniqueConstraint("negocio_id", "id", name="uq_loja_negocio_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Central de produção responsável por abastecer esta loja.
    central_producao_id: Mapped[int] = mapped_column(ForeignKey("centrais_producao.id"), nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # Nullable: lojas antigas não têm código até o admin preencher.
    codigo = mapped_column(String(32), nullable=True)

    # Horário do dia em que a rotina automática de zeragem deve rodar para
    # esta loja específica (ex.: 06:00). Configurável pelo admin da rede,
    # individualmente por loja.
    horario_zeragem: Mapped[time] = mapped_column(Time, nullable=False, default=time(6, 0))

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    negocio = relationship("Negocio", back_populates="lojas")
    central_producao = relationship("CentralProducao", back_populates="lojas")
    usuarios = relationship("Usuario", back_populates="loja")
