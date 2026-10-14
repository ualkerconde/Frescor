"""
Schemas da consulta de vendas e perdas diárias (SaaS web, Fase 2 / P6).
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class LojaResumo(BaseModel):
    id: int
    codigo: Optional[str] = None


class ProdutoResumo(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class ItemDiarioResponse(BaseModel):
    data: date
    loja: LojaResumo
    produto: ProdutoResumo
    quantidade: Decimal = Field(description="Na unidade do produto (UN: peças; KG: quilos), até 3 casas.")
    unidade: str = Field(description="UN ou KG.")
    origem: str = Field(description="manual (importação de CSV) ou api (integração com o PDV); perdas também inferida.")


class TotalPorUnidadeResponse(BaseModel):
    unidade: str = Field(description="UN ou KG.")
    quantidade: Decimal = Field(description="Soma no período, com os mesmos filtros, sem paginação.")


class ConsultaDiariaResponse(BaseModel):
    total: int = Field(description="Total de linhas que atendem aos filtros (todas as páginas).")
    limit: int
    offset: int
    itens: list[ItemDiarioResponse]
    totais: list[TotalPorUnidadeResponse] = Field(
        description="Soma do período por unidade (UN e KG não se somam), sem paginação. Vazio se não houver linhas."
    )
