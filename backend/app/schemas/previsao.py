"""
Schemas da API de previsão (Fase 3 / F8): gerar, consultar e qualidade.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class GerarPrevisoesRequest(BaseModel):
    data_referencia: Optional[date] = Field(
        None, description="Último dia com venda considerada (padrão: ontem). Prevê os 7 dias seguintes."
    )


class GeracaoResponse(BaseModel):
    data_referencia: date
    data_inicio: date
    data_fim: date
    gravadas: int = Field(description="Previsões gravadas (loja + produto + dia).")
    sem_previsao: int = Field(description="Das gravadas, quantas ficaram sem número (sem histórico e sem proxy).")
    substituidas: int = Field(description="Previsões da geração anterior que foram substituídas.")
    versao_metodo: str


class LojaPrevisao(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class ProdutoPrevisao(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class EventoAplicado(BaseModel):
    id: int
    nome: str
    tipo_ajuste: str
    valor_ajuste: Decimal


class PrevisaoItemResponse(BaseModel):
    data: date
    loja: LojaPrevisao
    produto: ProdutoPrevisao
    unidade: str = Field(description="UN ou KG.")
    previsao: Optional[Decimal] = Field(description="Número final; vazio = sem histórico e sem proxy.")
    previsao_sem_evento: Optional[Decimal]
    previsao_propria: Optional[Decimal] = Field(description="Só com o histórico do produto na loja.")
    venda_semana_passada: Optional[Decimal] = Field(
        description="Venda do mesmo dia da semana passada (vazio = a loja não tem dado daquele dia)."
    )
    metodo: str = Field(description="semanal ou sazonal.")
    estatistica: str = Field(description="Estatística da base (mediana, D25).")
    base: Optional[Decimal]
    semanas_na_base: int
    tendencia: Decimal
    tendencia_bruta: Optional[Decimal]
    dias_na_tendencia: int
    inicio_historico: Optional[date]
    peso_historico: Decimal = Field(description="0 a 1; menor que 1 = pouco histórico (cold start).")
    pouco_historico: bool
    proxy: Optional[Decimal]
    origem_proxy: Optional[str] = Field(description="outras_lojas, categoria ou unidade.")
    eventos: list[EventoAplicado]
    data_referencia: date
    gerado_em: datetime
    versao_metodo: str


class TotalPrevistoResponse(BaseModel):
    unidade: str
    previsto: Decimal
    vendido_semana_passada: Decimal


class PrevisoesResponse(BaseModel):
    data: date
    itens: list[PrevisaoItemResponse]
    totais: list[TotalPrevistoResponse] = Field(description="Por unidade (UN e KG não se somam).")


class QualidadeUnidadeResponse(BaseModel):
    unidade: str
    pares: int = Field(description="Quantos loja + produto + dia entraram na conta.")
    wape: Optional[Decimal] = Field(description="Σ|real − previsto| ÷ Σ real (0,11 = errou 11% do volume).")
    vies: Optional[Decimal] = Field(description="Σ(previsto − real) ÷ Σ real; positivo = sobra, negativo = falta.")
    ingenuo_wape: Optional[Decimal]
    ingenuo_vies: Optional[Decimal]
    vence_ingenuo: Optional[bool]


class QualidadeResponse(BaseModel):
    data_inicio: date
    data_fim: date
    por_unidade: list[QualidadeUnidadeResponse]
