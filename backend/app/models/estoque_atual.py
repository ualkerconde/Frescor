"""
Modelo da tabela `estoque_atual`.

Representa, EM CADA LOJA, dois valores distintos e com propósitos
diferentes para cada produto (ver especificação atualizada):

1. `quantidade_inventariada`: o RASCUNHO de trabalho do app — quantas
   peças/unidades o usuário contou na última contagem. É este campo que a
   rotina diária de zeragem zera (depois de copiar o valor para
   `historico_contagens`), só para facilitar a próxima contagem do
   usuário (ele não precisa zerar item a item manualmente).

2. `estoque_atual_calculado`: o valor REAL de estoque, exibido no
   software web. É recalculado a cada lançamento individual do app
   (nunca esperando o usuário "terminar tudo"), usando a unidade de
   medida, o peso médio e/ou o peso informado do produto:
     - UN                   -> estoque_atual_calculado = quantidade_inventariada
     - KG com peso médio    -> estoque_atual_calculado = peso_medio_kg * quantidade_inventariada
     - KG sem peso médio    -> estoque_atual_calculado = peso_informado_kg
   Este campo NUNCA é zerado pela rotina de zeragem — ele só muda quando
   há um novo lançamento, preservando o último valor real conhecido
   mesmo enquanto o app está com o rascunho zerado aguardando a próxima
   contagem.

3. `peso_informado_kg`: o peso pesado manualmente na última contagem,
   preenchido só quando o produto é KG e não tem peso médio cadastrado
   (ex.: bolo vendido por fatia). NULL nos demais casos.

O mesmo produto (ex.: "Pão Francês", produto_id=50) tem uma linha
INDEPENDENTE de estoque para cada loja em que é vendido — por isso a
unicidade é sobre o par (produto_id, loja_id), não apenas sobre produto_id.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EstoqueAtual(Base):
    __tablename__ = "estoque_atual"
    __table_args__ = (
        UniqueConstraint("produto_id", "loja_id", name="uq_estoque_produto_loja"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)

    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)

    # Mantido de forma redundante (também existe via produto.negocio_id e
    # via loja.negocio_id) de propósito: garante que toda consulta a esta
    # tabela possa filtrar diretamente por negocio_id, sem precisar de
    # JOIN, reduzindo o risco de uma consulta esquecer o filtro multiempresa.
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Rascunho: contagem de peças/unidades feita pelo usuário no app.
    # Sempre um número inteiro (não há contagem fracionária de peças).
    # Zerado pela rotina diária de zeragem.
    quantidade_inventariada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Valor real de estoque, calculado a partir de quantidade_inventariada
    # e da unidade de medida/peso médio do produto. Pode ser fracionário
    # (ex.: produtos em KG), por isso é Numeric, não Integer. NUNCA é
    # zerado pela rotina de zeragem.
    estoque_atual_calculado = mapped_column(Numeric(12, 4), default=0, nullable=False)

    # Peso pesado manualmente na última contagem, só preenchido quando o
    # produto é KG e não tem peso_medio_kg cadastrado (cenário 3). NULL
    # nos demais casos (UN ou KG com peso médio).
    peso_informado_kg = mapped_column(Numeric(10, 4), nullable=True)

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    produto = relationship("Produto")
    loja = relationship("Loja")
