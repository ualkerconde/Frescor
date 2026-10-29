"""
Schemas do cadastro mínimo de eventos (Fase 3 / F3, D24).
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.evento import EscopoLoja, EscopoProduto, TipoAjuste


class EventoCriar(BaseModel):
    nome: str
    data_inicio: date
    data_fim: date
    tipo_ajuste: TipoAjuste = Field(
        description="multiplicador: multiplica a previsão do dia (ex.: 1.5); "
        "valor_fixo: a previsão do dia por loja e produto passa a ser este valor."
    )
    valor_ajuste: Decimal
    escopo_loja: EscopoLoja = Field(
        EscopoLoja.ESPECIFICAS,
        description="todas: todas as lojas da central do gestor (D27), sem loja_ids; "
        "especificas: as lojas de loja_ids.",
    )
    loja_ids: Optional[list[int]] = Field(None, description="Lojas da central do gestor (com escopo especificas).")
    produto_ids: Optional[list[int]] = Field(None, description="Vazio ou ausente = todos os produtos.")


class EventoResponse(BaseModel):
    id: int
    nome: str
    data_inicio: date
    data_fim: date
    tipo_ajuste: TipoAjuste
    valor_ajuste: Decimal
    escopo_loja: EscopoLoja
    loja_ids: list[int] = Field(description="Só as lojas da central do gestor.")
    escopo_produto: EscopoProduto
    produto_ids: list[int]
    pode_apagar: bool = Field(
        True, description="False quando o evento vale também para lojas de outra central (apagar -> 403)."
    )
