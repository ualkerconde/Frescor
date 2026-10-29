"""
Schemas das rotas de apoio do SaaS web (/web/me, /web/lojas, /web/produtos).
"""

from typing import Optional

from pydantic import BaseModel, Field


class UsuarioResumo(BaseModel):
    id: int
    nome: str
    email: str


class CentralResumo(BaseModel):
    id: int
    nome: str


class NegocioResumo(BaseModel):
    id: int
    nome: str


class MeResponse(BaseModel):
    usuario: UsuarioResumo
    central: CentralResumo
    negocio: NegocioResumo


class LojaWebResponse(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str
    ativo: bool = Field(description="Lojas inativas aparecem (para consultar histórico), mas não aceitam importação (D12).")


class ProdutoWebResponse(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str
    unidade: str = Field(description="UN ou KG.")
    ativo: bool
    # Fase 6 (lista da tela de cadastro):
    tipo_abastecimento: str = Field("produzido", description="produzido ou distribuido.")
    setor: Optional[str] = Field(None, description="Nome do setor de produção (vazio = sem setor).")
    lojas_ativas: int = Field(0, description="Em quantas lojas da central do gestor o produto está ativo.")


class ProdutosWebResponse(BaseModel):
    total: int
    limit: int
    offset: int
    itens: list[ProdutoWebResponse]
