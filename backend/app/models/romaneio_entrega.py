"""
Modelo da tabela `romaneios_entregas` (Fase 5 / E1; migration 0024).

Uma entrega por loja no romaneio: é o "pacote" que sai da central para a
loja e que a loja confirma no app. Existe porque a saída e o recebimento
acontecem loja a loja (D76, D77), não para o romaneio inteiro de uma vez.
Não há rota no V1 (D74).

Situação:
- `aguardando_saida`: romaneio gerado, nada saiu ainda;
- `expedida`: a central registrou a saída (quem, quando). A quantidade
  expedida é a final dos itens (D76);
- `recebida`: a loja confirmou no app (quem, quando), com ou sem
  diferença nos itens (D78).
O banco confere que cada situação tem exatamente os campos dela
(`ck_entrega_situacao_coerente`).

"Sem confirmação" (D79) não é gravado: é a entrega `expedida` cujo dia de
entrega já terminou, calculado na leitura. Ela conta como recebida pela
quantidade final do romaneio e aparece marcada para o gestor.

Isolamento (D2): FKs compostas com o romaneio e a loja do mesmo negócio.
Apagar o romaneio apaga as entregas (CASCADE).
"""

import enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SituacaoEntrega(str, enum.Enum):
    AGUARDANDO_SAIDA = "aguardando_saida"
    EXPEDIDA = "expedida"
    RECEBIDA = "recebida"


class RomaneioEntrega(Base):
    __tablename__ = "romaneios_entregas"
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_entrega_negocio_id"),
        UniqueConstraint("romaneio_id", "loja_id", name="uq_entrega_romaneio_loja"),
        CheckConstraint(
            "(situacao = 'aguardando_saida' AND expedido_em IS NULL AND expedido_por_usuario_id IS NULL"
            " AND recebido_em IS NULL AND recebido_por_usuario_id IS NULL)"
            " OR (situacao = 'expedida' AND expedido_em IS NOT NULL AND expedido_por_usuario_id IS NOT NULL"
            " AND recebido_em IS NULL AND recebido_por_usuario_id IS NULL)"
            " OR (situacao = 'recebida' AND expedido_em IS NOT NULL AND expedido_por_usuario_id IS NOT NULL"
            " AND recebido_em IS NOT NULL AND recebido_por_usuario_id IS NOT NULL)",
            name="ck_entrega_situacao_coerente",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "romaneio_id"], ["romaneios.negocio_id", "romaneios.id"],
            name="fk_entrega_negocio_romaneio", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_entrega_negocio_loja",
        ),
        Index("ix_entregas_loja_situacao", "negocio_id", "loja_id", "situacao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    romaneio_id: Mapped[int] = mapped_column(ForeignKey("romaneios.id", ondelete="CASCADE"), nullable=False)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    situacao: Mapped[SituacaoEntrega] = mapped_column(
        Enum(SituacaoEntrega, name="situacaoentregaromaneio",
             values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False, default=SituacaoEntrega.AGUARDANDO_SAIDA,
        server_default=SituacaoEntrega.AGUARDANDO_SAIDA.value,
    )
    # Datas e horas em UTC sem fuso (como o app grava a contagem).
    expedido_em = mapped_column(DateTime, nullable=True)
    expedido_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    recebido_em = mapped_column(DateTime, nullable=True)
    recebido_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    observacao = mapped_column(String(255), nullable=True)
