"""
Schemas dos cadastros do SaaS web (Fase 6): central, setores de produção,
produto (com calendário e vigência) e habilitação do produto por loja.

Nas rotas de edição (PATCH), só os campos ENVIADOS mudam: um campo ausente
fica como está; `null` num campo opcional apaga o valor.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.calendario_producao import DiaSemana
from app.models.produto import CicloPrevisao, TipoAbastecimento, UnidadeMedida

# ---------------------------------------------------------------- central


class CentralResponse(BaseModel):
    id: int
    nome: str
    secao: str = Field(description="padaria, acougue ou hortifruti (D14); só leitura.")
    prazo_entrega_dias: int = Field(description="Dias entre a produção e a entrega na loja (0 = no mesmo dia).")
    ativa: bool = Field(description="Só leitura (D103).")
    lojas: int = Field(description="Lojas da central (ativas e inativas).")


class CentralEditar(BaseModel):
    nome: Optional[str] = None
    prazo_entrega_dias: Optional[int] = Field(None, description="0 a 7 dias; vale para as ordens geradas depois.")


# ---------------------------------------------------------------- setores


class SetorCriar(BaseModel):
    nome: str
    ordem: Optional[int] = Field(None, description="Posição na lista e nas folhas; ausente = no fim.")


class SetorEditar(BaseModel):
    nome: Optional[str] = None
    ordem: Optional[int] = None
    ativo: Optional[bool] = None


# ---------------------------------------------------------------- produto


class _CamposProduto(BaseModel):
    codigo_barras: Optional[str] = None
    unidade_medida: Optional[UnidadeMedida] = None
    peso_medio_kg: Optional[Decimal] = Field(None, description="Só em KG: peso de uma peça, em kg (até 4 casas).")
    ativo: Optional[bool] = None
    tipo_abastecimento: Optional[TipoAbastecimento] = None
    dias_validade: Optional[int] = Field(None, description="Dias após a fabricação (1 a 365); vazio = sem limite.")
    margem_maxima_percentual: Optional[Decimal] = Field(None, description="0 a 500 (%); vazio = 10% (D34).")
    data_inicio_vigencia: Optional[date] = None
    data_fim_vigencia: Optional[date] = None
    vigencia_recorrente: Optional[bool] = Field(None, description="Sazonal: a temporada se repete todo ano (D105).")
    ciclo_previsao: Optional[CicloPrevisao] = None
    setor_producao_id: Optional[int] = Field(None, description="Setor ativo da central do gestor; vazio = sem setor.")
    dias_producao: Optional[list[DiaSemana]] = Field(
        None, description="Dias da semana em que a central produz (ou envia); vazio = todos os dias."
    )


class ProdutoCriar(_CamposProduto):
    nome: str
    codigo: str = Field(description="Obrigatório e único no negócio (D97).")
    habilitar_lojas: bool = Field(True, description="Já ativo em todas as lojas ativas da central (D101).")


class ProdutoEditar(_CamposProduto):
    nome: Optional[str] = None
    codigo: Optional[str] = None


class SetorDoProduto(BaseModel):
    id: int
    nome: str


class ProdutoDetalheResponse(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str
    codigo_barras: Optional[str] = None
    unidade: str
    peso_medio_kg: Optional[Decimal] = None
    ativo: bool
    tipo_abastecimento: TipoAbastecimento
    dias_validade: Optional[int] = None
    margem_maxima_percentual: Optional[Decimal] = None
    data_inicio_vigencia: Optional[date] = None
    data_fim_vigencia: Optional[date] = None
    vigencia_recorrente: bool
    ciclo_previsao: CicloPrevisao
    setor: Optional[SetorDoProduto] = None
    dias_producao: list[DiaSemana] = Field(description="Vazio = todos os dias.")
    tem_historico: bool = Field(description="Com histórico, a unidade não pode mudar (D98).")


# ---------------------------------------------------------------- lojas do produto


class LojaDoProdutoResponse(BaseModel):
    loja_id: int
    codigo: Optional[str] = None
    nome: str
    loja_ativa: bool
    habilitado: bool = Field(description="Existe a habilitação (mesmo desativada).")
    ativo: bool = Field(description="O produto está ativo nesta loja (aparece no app, na previsão e na ordem).")


class LojaDoProdutoEditar(BaseModel):
    ativo: bool
