"""
Modelo da tabela `ordens_producao_linhas` (Fase 4 / N5; migration 0022).

Uma linha por loja em cada item da ordem: quanto mandar para aquela loja.

- `quantidade_sugerida`: a necessidade calculada (N3/N4), já arredondada
  (D37). NULL quando não havia como calcular (sem previsão, sem
  calendário...): o gestor informa.
- `quantidade_final`: a decisão do gestor (NULL = ainda não informada).
  Guardar as duas lado a lado é o que permite, na Fase 7, medir a
  divergência entre a sugestão do sistema e a decisão humana.
- `componentes` (JSON): a conta inteira (cobertura, previsão somada,
  margem, alvo, contagem e quando foi feita, trânsito, projeção até a
  chegada) para o "Ver a conta" da tela. `avisos` (JSON) à parte, para a
  tela listar o que precisa de atenção.
- Edição: quem, quando e motivo opcional (só a última edição).
- Recebimento: não fica aqui. A loja confirma no romaneio
  (`romaneios_entregas`, `romaneios_itens`); as colunas de recebimento
  desta tabela saíram na 0025 (D75, D79).

A loja precisa ser da central da ordem: regra do serviço (o vínculo
loja-central pode mudar com o tempo; o banco não o congela).

Isolamento (D2): FKs compostas com o item e a loja do mesmo negócio.
Apagar o item (ou a ordem) apaga as linhas (CASCADE).
"""

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrdemProducaoLinha(Base):
    __tablename__ = "ordens_producao_linhas"
    __table_args__ = (
        UniqueConstraint("item_id", "loja_id", name="uq_ordem_linha_item_loja"),
        UniqueConstraint("negocio_id", "id", name="uq_ordem_linha_negocio_id"),  # alvo do item do romaneio (0024)
        CheckConstraint(
            "quantidade_sugerida IS NULL OR quantidade_sugerida >= 0", name="ck_ordem_linha_sugerida_nao_negativa"
        ),
        CheckConstraint("quantidade_final IS NULL OR quantidade_final >= 0", name="ck_ordem_linha_final_nao_negativa"),
        ForeignKeyConstraint(
            ["negocio_id", "item_id"], ["ordens_producao_itens.negocio_id", "ordens_producao_itens.id"],
            name="fk_ordem_linha_negocio_item", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_ordem_linha_negocio_loja",
        ),
        Index("ix_ordem_linhas_loja", "negocio_id", "loja_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("ordens_producao_itens.id", ondelete="CASCADE"), nullable=False)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    quantidade_sugerida = mapped_column(Numeric(12, 3), nullable=True)
    quantidade_final = mapped_column(Numeric(12, 3), nullable=True)
    componentes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    avisos: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    editado_em = mapped_column(DateTime, nullable=True)
    editado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    motivo_edicao = mapped_column(String(255), nullable=True)
