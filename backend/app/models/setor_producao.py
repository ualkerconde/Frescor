"""
Modelo da tabela `setores_producao` (Fase 4 / N9b, D67; migration 0023).

O setor é a divisão da produção dentro de uma central: a bancada de pães,
a de bolos, a de biscoitos. É diferente da SEÇÃO da D14 (padaria, açougue,
hortifruti), que é a central inteira.

Para que serve: a ordem aprovada é impressa com uma folha por setor, e cada
equipe recebe só a sua folha (D67). O gestor escolhe quais setores
imprimir; produto sem setor sai na folha "Sem setor".

Por central (cada central organiza a sua produção); `ordem` define a
sequência das folhas e da lista na tela; `ativo` tira o setor da escolha
sem apagar (produtos de setor inativo saem em "Sem setor").

Isolamento (D2): FK composta com a central do mesmo negócio.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SetorProducao(Base):
    __tablename__ = "setores_producao"
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_setor_negocio_id"),
        UniqueConstraint("central_producao_id", "nome", name="uq_setor_central_nome"),
        CheckConstraint("btrim(nome) <> ''", name="ck_setor_nome_preenchido"),
        ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"], ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_setor_negocio_central",
        ),
        Index("ix_setores_central", "negocio_id", "central_producao_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    central_producao_id: Mapped[int] = mapped_column(ForeignKey("centrais_producao.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
