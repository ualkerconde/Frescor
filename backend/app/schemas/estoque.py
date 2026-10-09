"""
Schemas (formatos de dados) usados pelos endpoints de produtos e estoque.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ClassificacaoItem(BaseModel):
    """
    Um nível de classificação já resolvido para exibição: o nome do nível
    (configurado por negócio, ex.: "Departamento") e o valor atribuído ao
    produto naquele nível (ex.: "Padaria"). A lista de ClassificacaoItem
    de um produto vem sempre ordenada pela ordem do nível (1 a 4).
    """

    nivel: str
    ordem: int
    valor: str

    class Config:
        from_attributes = True


class ProdutoComEstoqueResponse(BaseModel):
    id: int
    nome: str
    codigo: Optional[str] = None
    codigo_barras: Optional[str] = None
    unidade_medida: str
    quantidade_inventariada: int
    estoque_atual_calculado: Decimal
    peso_informado_kg: Optional[Decimal] = None
    requer_peso_informado: bool = Field(
        default=False,
        description=(
            "True quando o produto é KG e não tem peso médio cadastrado — o app "
            "deve pedir o peso pesado na hora (ex.: bolo vendido por fatia) em vez "
            "de calcular pelo peso médio."
        ),
    )
    classificacao: list[ClassificacaoItem] = Field(
        default_factory=list,
        description=(
            "Níveis de classificação do produto (até 4), configurados por "
            "negócio e ordenados do mais genérico ao mais específico. Lista "
            "vazia quando o negócio não configurou níveis ou o produto não "
            "foi classificado."
        ),
    )

    class Config:
        from_attributes = True


class AtualizarEstoqueRequest(BaseModel):
    quantidade_inventariada: int = Field(
        ge=0, description="Quantidade de peças/unidades contadas. Não pode ser negativa."
    )
    peso_informado_kg: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description=(
            "Peso (kg) pesado manualmente na contagem. Só é aceito para produtos "
            "KG sem peso médio cadastrado; para os demais, envie null."
        ),
    )


class EstoqueResponse(BaseModel):
    produto_id: int
    quantidade_inventariada: int
    estoque_atual_calculado: Decimal
    peso_informado_kg: Optional[Decimal] = None
    atualizado_em: datetime

    class Config:
        from_attributes = True


class ContagemOffline(BaseModel):
    produto_id: int
    quantidade: int = Field(ge=0)
    peso_informado_kg: Optional[Decimal] = Field(default=None, ge=0)
    registrado_em_local: datetime


class SincronizarEstoqueRequest(BaseModel):
    contagens: list[ContagemOffline]


class SincronizarEstoqueResponse(BaseModel):
    sincronizados: int
    produto_ids: list[int]
