"""
Modelo da tabela `ordens_producao_itens` (Fase 4 / N5, doc §3.9; migration 0022).

Um item por produto em cada ordem. Guarda o tipo de abastecimento e a
unidade do produto NO MOMENTO da geração: se o cadastro mudar depois, a
ordem antiga continua coerente. A ordem guarda os dois tipos (D39): a tela
de produção mostra os produzidos; os distribuídos vão para o romaneio
(Fase 5).

A quantidade planejada NÃO é gravada aqui: é a soma das linhas por loja
(`ordens_producao_linhas`). Gravar a soma ao lado das parcelas abriria
espaço para as duas divergirem depois de uma edição.

`quantidade_produzida`: produção real, preenchida na Fase 5 (pode ficar
abaixo do planejado; o rateio em escassez é decisão do gestor, regra de
ouro 4).

Isolamento (D2): FKs compostas com a ordem e o produto do mesmo negócio.
Apagar a ordem apaga os itens (CASCADE).
"""

from sqlalchemy import CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.produto import TipoAbastecimento, UnidadeMedida


class OrdemProducaoItem(Base):
    __tablename__ = "ordens_producao_itens"
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_ordem_item_negocio_id"),
        UniqueConstraint("ordem_id", "produto_id", name="uq_ordem_item_produto"),
        CheckConstraint(
            "quantidade_produzida IS NULL OR quantidade_produzida >= 0", name="ck_ordem_item_produzida_nao_negativa"
        ),
        ForeignKeyConstraint(
            ["negocio_id", "ordem_id"], ["ordens_producao.negocio_id", "ordens_producao.id"],
            name="fk_ordem_item_negocio_ordem", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_ordem_item_negocio_produto",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    ordem_id: Mapped[int] = mapped_column(ForeignKey("ordens_producao.id", ondelete="CASCADE"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    tipo_abastecimento: Mapped[TipoAbastecimento] = mapped_column(
        Enum(TipoAbastecimento, name="tipoabastecimento", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    unidade: Mapped[UnidadeMedida] = mapped_column(
        Enum(UnidadeMedida, name="unidademedida", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    # Produção real (Fase 5); NULL até lá.
    quantidade_produzida = mapped_column(Numeric(12, 3), nullable=True)
