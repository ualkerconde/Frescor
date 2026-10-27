"""
Schemas da API da ordem de produção (Fase 4 / N7).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class GerarOrdemRequest(BaseModel):
    data_producao: Optional[date] = Field(
        None, description="Dia de produção (AAAA-MM-DD), de hoje até 6 dias à frente; padrão: amanhã."
    )


class GeracaoOrdemResponse(BaseModel):
    ordem_id: int
    data_producao: date
    data_entrega: date
    itens: int = Field(description="Produtos na ordem (produzidos e distribuídos).")
    linhas: int = Field(description="Linhas loja + produto.")
    sem_quantidade: int = Field(description="Linhas sem sugestão (sem previsão, sem calendário...): informar.")
    substituiu_rascunho: bool = Field(description="Havia um rascunho do dia e ele foi substituído (ajustes perdidos).")
    previsao_atualizada: bool = Field(description="A previsão estava desatualizada e foi gerada de novo (D41).")


class EditarLinhaRequest(BaseModel):
    quantidade_final: Decimal = Field(description="Quantidade que a loja vai receber (UN inteiro; KG até 3 casas).")
    motivo: Optional[str] = Field(None, max_length=255, description="Motivo do ajuste (opcional).")


class LojaOrdem(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class ProdutoOrdem(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class TotalUnidadeResponse(BaseModel):
    unidade: str
    sugerido: Decimal
    final: Decimal


class LinhaOrdemResponse(BaseModel):
    id: int
    loja: LojaOrdem
    quantidade_sugerida: Optional[Decimal] = Field(description="Vazio = não havia como calcular; informar.")
    quantidade_final: Optional[Decimal]
    editada: bool
    editado_em: Optional[datetime]
    motivo_edicao: Optional[str]
    avisos: list[str]
    componentes: dict[str, Any] = Field(description="A conta da necessidade (para o 'Ver a conta').")


class ItemOrdemResponse(BaseModel):
    id: int
    produto: ProdutoOrdem
    tipo_abastecimento: str = Field(description="produzido ou distribuido.")
    unidade: str
    total_sugerido: Decimal
    total_final: Decimal = Field(description="Soma das finais das lojas (D54).")
    linhas: list[LinhaOrdemResponse]


class OrdemResumoResponse(BaseModel):
    id: int
    data_producao: date
    data_entrega: date
    tipo: str
    status: str = Field(description="rascunho ou aprovada.")
    versao_metodo: str
    referencia_previsao: Optional[date]
    gerado_em: datetime
    gerado_por: Optional[str]
    aprovado_em: Optional[datetime]
    aprovado_por: Optional[str]
    linhas: int
    linhas_editadas: int = Field(description="Linhas ajustadas pelo gestor (perdidas se o rascunho for regerado).")
    linhas_sem_quantidade: int
    totais: list[TotalUnidadeResponse]


class OrdemDetalheResponse(OrdemResumoResponse):
    itens: list[ItemOrdemResponse]


class OrdensDoDiaResponse(BaseModel):
    data_producao: date
    ordens: list[OrdemResumoResponse]


class SetorResponse(BaseModel):
    id: int
    nome: str
    ordem: int = Field(description="Ordem de exibição (das folhas impressas e da lista na tela).")
    ativo: bool
