"""
Modelo da tabela `niveis_classificacao`.

Define, POR NEGÓCIO (tenant), até 4 níveis de classificação de produtos,
com nome configurável e ordem fixa (1 a 4). Exemplos reais de uso, cada
um definido pelo próprio negócio:

    Empresa A: 1=Departamento, 2=Seção, 3=Categoria, 4=Subcategoria
    Empresa B: 1=Setor
    Empresa C: 1=Linha, 2=Família
    Empresa D: 1=Categoria, 2=Subcategoria

Um negócio pode usar de 1 a 4 níveis — não é obrigatório preencher todos
os 4. A validação de "no máximo 4 níveis por negócio" e de "ordem única
dentro do negócio" é feita na camada de serviço, mas também reforçada no
banco pela constraint de unicidade (negocio_id, ordem) e pelo check de
ordem entre 1 e 4.

Esta tabela é gerenciada pelo software web (fora deste backend, que é
somente leitura para produtos e sua classificação — mesmo racional do
catálogo de produtos, ver app/models/produto.py).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class NivelClassificacao(Base):
    __tablename__ = "niveis_classificacao"
    __table_args__ = (
        # Garante, no nível do banco, que um negócio não tenha dois níveis
        # com a mesma ordem (ex.: dois níveis "ordem=1").
        UniqueConstraint("negocio_id", "ordem", name="uq_nivel_negocio_ordem"),
        # Garante que a ordem esteja sempre dentro do intervalo suportado
        # (até 4 níveis de classificação por negócio).
        CheckConstraint("ordem >= 1 AND ordem <= 4", name="ck_nivel_ordem_1_a_4"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Posição do nível na hierarquia (1 = mais genérico, 4 = mais
    # específico). Fixa por posição — o que varia por negócio é apenas o
    # nome dado a cada posição.
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    # Nome do nível, definido livremente por cada negócio
    # (ex.: "Departamento", "Setor", "Linha").
    nome: Mapped[str] = mapped_column(String(100), nullable=False)

    # Permite desativar um nível sem apagar o histórico de classificações
    # já atribuídas com base nele (ver app/models/produto_classificacao.py).
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    negocio = relationship("Negocio", back_populates="niveis_classificacao")
