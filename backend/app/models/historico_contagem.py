"""
Modelo da tabela `historico_contagens`.

Snapshot diário da contagem de cada produto, EM CADA LOJA, criado pela
rotina de zeragem ANTES de zerar `estoque_atual.quantidade_inventariada`.
É a base para os relatórios futuros (ex.: cálculo de consumo/vendas pela
diferença de estoque entre dias, por loja). Esta tabela nunca é apagada ou
sobrescrita — apenas cresce com o tempo.

Guardamos tanto a contagem de peças (quantidade_inventariada) quanto o
valor real já calculado (estoque_atual_calculado) no momento do snapshot,
para que relatórios futuros não precisem reconstruir esse cálculo a
partir do peso médio do produto na época (que pode ter mudado desde então).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class HistoricoContagem(Base):
    __tablename__ = "historico_contagens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Contagem de peças/unidades no momento do snapshot (o que estava em
    # estoque_atual.quantidade_inventariada antes de ser zerado).
    quantidade_inventariada: Mapped[int] = mapped_column(Integer, nullable=False)

    # Valor real (em UN ou KG, conforme a unidade de medida do produto) no
    # momento do snapshot (o que estava em estoque_atual.estoque_atual_calculado).
    estoque_atual_calculado = mapped_column(Numeric(12, 4), nullable=False)

    # Peso informado manualmente no momento do snapshot (o que estava em
    # estoque_atual.peso_informado_kg). Só é preenchido para produtos KG
    # sem peso médio cadastrado; NULL nos demais casos.
    peso_informado_kg = mapped_column(Numeric(10, 4), nullable=True)

    # Data/hora a que este snapshot se refere (momento em que a zeragem
    # daquela loja específica ocorreu)
    data_referencia: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    produto = relationship("Produto")
    loja = relationship("Loja")
