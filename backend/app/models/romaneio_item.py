"""
Modelo da tabela `romaneios_itens` (Fase 5 / E1, doc §3.11; migration 0024).

Um item por produto em cada entrega (loja): quanto mandar e quanto chegou.

- `quantidade_sugerida`: do sistema. Igual à final da ordem quando a
  produção real cobre o planejado; rateio proporcional quando falta (D70).
- `quantidade_final`: decisão do gestor (D71). É a quantidade expedida
  (D76) e a que entra no trânsito da necessidade (D79). Guardar as duas lado
  a lado permite medir, na Fase 7, a divergência sugestão × decisão.
- `quantidade_recebida` e `motivo_divergencia`: da loja, no app (D77, D78).
  Recebida = o que entrou bom na loja. Diferente da final exige motivo
  (falta, avaria, a mais, outro); motivo sem recebida é recusado
  (`ck_romaneio_item_divergencia_coerente`).
- `ordem_linha_id`: a linha da ordem de onde o item veio (uma vez só), para
  ligar o plano (ordem) ao que foi mandado (romaneio).
- Edição: quem, quando e motivo opcional (só a última, como na ordem, D56).

Isolamento (D2): FKs compostas com a entrega, o produto e a linha da ordem
do mesmo negócio. Apagar a entrega (ou o romaneio) apaga os itens (CASCADE).
"""

import enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.produto import UnidadeMedida


class MotivoDivergencia(str, enum.Enum):
    FALTA = "falta"
    AVARIA = "avaria"
    A_MAIS = "a_mais"
    OUTRO = "outro"


class RomaneioItem(Base):
    __tablename__ = "romaneios_itens"
    __table_args__ = (
        UniqueConstraint("entrega_id", "produto_id", name="uq_romaneio_item_entrega_produto"),
        UniqueConstraint("ordem_linha_id", name="uq_romaneio_item_ordem_linha"),
        CheckConstraint("quantidade_sugerida >= 0", name="ck_romaneio_item_sugerida_nao_negativa"),
        CheckConstraint("quantidade_final >= 0", name="ck_romaneio_item_final_nao_negativa"),
        CheckConstraint(
            "quantidade_recebida IS NULL OR quantidade_recebida >= 0", name="ck_romaneio_item_recebida_nao_negativa"
        ),
        CheckConstraint(
            "(quantidade_recebida IS NULL AND motivo_divergencia IS NULL)"
            " OR (quantidade_recebida IS NOT NULL"
            " AND (quantidade_recebida = quantidade_final OR motivo_divergencia IS NOT NULL))",
            name="ck_romaneio_item_divergencia_coerente",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "entrega_id"], ["romaneios_entregas.negocio_id", "romaneios_entregas.id"],
            name="fk_romaneio_item_negocio_entrega", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"],
            name="fk_romaneio_item_negocio_produto",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "ordem_linha_id"], ["ordens_producao_linhas.negocio_id", "ordens_producao_linhas.id"],
            name="fk_romaneio_item_negocio_linha",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("romaneios_entregas.id", ondelete="CASCADE"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    ordem_linha_id: Mapped[int] = mapped_column(ForeignKey("ordens_producao_linhas.id"), nullable=False)
    unidade: Mapped[UnidadeMedida] = mapped_column(
        Enum(UnidadeMedida, name="unidademedida", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    quantidade_sugerida = mapped_column(Numeric(12, 3), nullable=False)
    quantidade_final = mapped_column(Numeric(12, 3), nullable=False)
    quantidade_recebida = mapped_column(Numeric(12, 3), nullable=True)
    motivo_divergencia = mapped_column(
        Enum(MotivoDivergencia, name="motivodivergenciarecebimento",
             values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,
    )
    observacao_divergencia = mapped_column(String(255), nullable=True)
    editado_em = mapped_column(DateTime, nullable=True)
    editado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    motivo_edicao = mapped_column(String(255), nullable=True)
