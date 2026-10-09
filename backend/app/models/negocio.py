"""
Modelo da tabela `negocios`.

Cada linha representa um negócio-cliente (uma rede/empresa) que usa a
plataforma. Esta é a tabela "raiz" do isolamento multiempresa: praticamente
todas as outras tabelas relevantes do sistema referenciam um negocio_id.

Um negócio pode ter múltiplas lojas (ver app/models/loja.py). O horário de
zeragem diária NÃO fica aqui — fica em cada loja individualmente, já que
lojas diferentes da mesma rede podem ter rotinas diferentes.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Negocio(Base):
    __tablename__ = "negocios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos (permitem acessar negocio.usuarios, negocio.produtos, etc.
    # a partir do Python, sem escrever a query manualmente)
    lojas = relationship("Loja", back_populates="negocio")
    usuarios = relationship("Usuario", back_populates="negocio")
    produtos = relationship("Produto", back_populates="negocio")
    niveis_classificacao = relationship("NivelClassificacao", back_populates="negocio")
    centrais_producao = relationship("CentralProducao", back_populates="negocio")
