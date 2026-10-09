"""
Modelo da tabela `produto_classificacoes`.

Associa um produto a um valor de classificação para um nível específico
(ver app/models/nivel_classificacao.py). Cada linha representa "este
produto, neste nível, tem este valor" — por exemplo:
(produto_id=50, nivel_id=<Categoria>, valor="Pães").

Um produto pode ter de 1 a 4 linhas aqui, de acordo com quantos níveis o
negócio dele tiver configurado — não é obrigatório preencher todos os
níveis disponíveis. A checagem de que o nível pertence ao MESMO negócio
do produto é feita na camada de serviço (nunca confiar apenas na FK),
seguindo o mesmo racional de isolamento usado em produto_loja.py.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ProdutoClassificacao(Base):
    __tablename__ = "produto_classificacoes"
    __table_args__ = (
        # Um produto não pode ter dois valores para o mesmo nível.
        UniqueConstraint("produto_id", "nivel_id", name="uq_produto_classificacao_nivel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    nivel_id: Mapped[int] = mapped_column(ForeignKey("niveis_classificacao.id"), nullable=False, index=True)

    valor: Mapped[str] = mapped_column(String(255), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    produto = relationship("Produto", back_populates="classificacoes")
    nivel = relationship("NivelClassificacao")
