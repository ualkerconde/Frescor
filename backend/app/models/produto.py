"""
Modelo da tabela `produtos`.

Cadastrados e gerenciados exclusivamente pelo software web. O app móvel
(PWA) apenas lê esta tabela — nunca cria, edita ou remove produtos.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UnidadeMedida(str, enum.Enum):
    UN = "UN"
    KG = "KG"


class CicloPrevisao(str, enum.Enum):
    SEMANAL = "semanal"
    SAZONAL = "sazonal"


class Produto(Base):
    __tablename__ = "produtos"
    # Alvo das FKs compostas de vendas_diarias/perdas_diarias (migration
    # 0015): garante no banco que venda/perda e produto são do mesmo negócio.
    __table_args__ = (
        UniqueConstraint("negocio_id", "id", name="uq_produto_negocio_id"),
        # O código identifica o produto na importação de CSV (D7); único no
        # negócio para não haver linha ambígua (migration 0016).
        UniqueConstraint("negocio_id", "codigo", name="uq_produto_negocio_codigo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # Código interno do negócio (opcional). Independente do código de barras.
    # Permite que negócios com sistemas de codificação próprios identifiquem
    # seus produtos. Indexado para busca eficiente.
    codigo = mapped_column(String(64), nullable=True, index=True)

    # Código de barras (opcional). Usado pelo scanner de câmera.
    # Não usamos Mapped[Optional[str]] por incompatibilidade entre
    # SQLAlchemy 2.0.36 e Python 3.14 ao processar anotações Union.
    codigo_barras = mapped_column(String(64), nullable=True, index=True)

    # Unidade de medida:
    #   UN -> estoque_atual_calculado = quantidade_inventariada
    #   KG -> estoque_atual_calculado = peso_medio_kg * quantidade_inventariada
    unidade_medida: Mapped[UnidadeMedida] = mapped_column(
        Enum(UnidadeMedida, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=UnidadeMedida.UN,
        nullable=False,
    )

    # Peso médio de UMA peça em kg. Obrigatório (validado na camada de
    # serviço) apenas quando unidade_medida == KG.
    peso_medio_kg = mapped_column(Numeric(10, 4), nullable=True)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Campos de produção / ciclo de vida ---

    # True para produtos fabricados na central; False para itens só distribuídos.
    tem_producao_propria: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Prazo de validade em dias após a fabricação (opcional).
    dias_validade = mapped_column(Integer, nullable=True)

    # Percentual sobre o estoque mínimo calculado para derivar o máximo (opcional).
    margem_maxima_percentual = mapped_column(Numeric(6, 2), nullable=True)

    # Vigência: define se o produto é permanente, sazonal ou temporário.
    # Nulo = produto permanente (sem data de início ou fim definida).
    data_inicio_vigencia = mapped_column(Date, nullable=True)
    data_fim_vigencia = mapped_column(Date, nullable=True)

    # True = sazonal (repete todo ano no mesmo período); False = descontinuado
    # definitivamente a partir de data_fim_vigencia.
    vigencia_recorrente: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Ciclo de previsão: semanal (padrão) ou sazonal (evento específico do calendário).
    ciclo_previsao: Mapped[CicloPrevisao] = mapped_column(
        Enum(CicloPrevisao, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=CicloPrevisao.SEMANAL,
        nullable=False,
    )

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    negocio = relationship("Negocio", back_populates="produtos")
    classificacoes = relationship("ProdutoClassificacao", back_populates="produto")
