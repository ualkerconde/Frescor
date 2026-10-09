"""
Modelo da tabela `produtos_lojas`.

Tabela de habilitação: define quais produtos (do catálogo da rede) cada
loja pode efetivamente contar. Esta é a estrutura por trás da "matriz"
(produtos nas linhas, lojas nas colunas) que o administrador configura no
software web — embora a construção dessa tela em si esteja fora do escopo
deste backend de coleta (ela vive no software web).

Regra: a simples existência de uma linha aqui (produto_id, loja_id) já
significa "habilitado". Não há necessidade de uma coluna booleana
separada — desabilitar um produto para uma loja é apenas remover a linha
correspondente.

Importante (ver pedido original do usuário): um produto do negócio X não
pode, em nenhuma hipótese, ser habilitado para uma loja de outro negócio.
Essa checagem é feita na camada de serviço (nunca confiar apenas na FK),
sempre validando que loja.negocio_id == produto.negocio_id antes de
permitir a habilitação.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProdutoLoja(Base):
    __tablename__ = "produtos_lojas"
    __table_args__ = (
        # Garante, no nível do banco, que não exista habilitação duplicada
        # do mesmo produto para a mesma loja.
        UniqueConstraint("produto_id", "loja_id", name="uq_produto_loja"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)

    # Liga/desliga o produto para esta loja individualmente, sem afetar
    # as demais lojas. False = produto visível mas temporariamente inativo
    # nesta loja; remover a linha desabilita permanentemente.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
