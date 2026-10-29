"""
Schemas da API da distribuição do SaaS web (Fase 5 / E6) e do recebimento
no app (Fase 5 / E7).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class LojaRef(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


class ProdutoRef(BaseModel):
    id: int
    codigo: Optional[str] = None
    nome: str


# ---------------------------------------------------------------- produção real (D69)

class QuantidadeItem(BaseModel):
    item_id: int = Field(description="Item (produto) da ordem.")
    quantidade: Decimal = Field(description="Produzido (ou disponível, no distribuído). UN inteiro; KG até 3 casas.")


class RegistrarProducaoRequest(BaseModel):
    itens: list[QuantidadeItem] = Field(min_length=1)


class RegistrarProducaoResponse(BaseModel):
    itens_registrados: int
    romaneio_desatualizado: bool = Field(
        description="Havia um rascunho do romaneio: ele não foi refeito; use 'Gerar de novo' (D87).")


# ---------------------------------------------------------------- romaneio

class GerarRomaneioRequest(BaseModel):
    ordem_id: int


class GeracaoRomaneioResponse(BaseModel):
    romaneio_id: int
    ordem_id: int
    entregas: int
    itens: int
    produtos_com_escassez: list[int] = Field(description="Produção abaixo do planejado: rateio (D70).")
    produtos_com_sobra: list[int] = Field(description="Produção acima do planejado: a sobra fica na central.")
    substituiu_rascunho: bool


class ItemProducaoResponse(BaseModel):
    item_id: int
    produto: ProdutoRef
    unidade: str
    tipo_abastecimento: str
    planejado: Decimal = Field(description="Soma das finais da ordem (D54).")
    produzido: Optional[Decimal] = Field(description="Vazio = produção ainda não registrada.")
    registrado_em: Optional[datetime]


class ResumoRomaneioResponse(BaseModel):
    id: int
    status: str = Field(description="rascunho ou aprovado.")
    entregas: int
    situacoes: dict[str, int] = Field(
        description="Entregas por situação: aguardando_saida, a_caminho, sem_confirmacao, recebida, "
                    "confirmada_com_atraso.")


class OrdemDistribuicaoResponse(BaseModel):
    ordem_id: int
    data_producao: date
    data_entrega: date
    status_ordem: str = Field(description="rascunho ou aprovada (só a aprovada gera romaneio).")
    itens: list[ItemProducaoResponse]
    romaneio: Optional[ResumoRomaneioResponse]


class DistribuicaoDoDiaResponse(BaseModel):
    data_entrega: date
    ordens: list[OrdemDistribuicaoResponse]


class SituacaoEntregaResponse(BaseModel):
    situacao: str = Field(
        description="aguardando_saida, a_caminho, sem_confirmacao, recebida ou confirmada_com_atraso (D79, D85).")
    pode_confirmar: bool = Field(description="A loja ainda pode confirmar (até o fim do dia seguinte, D85).")
    com_diferenca: bool


class ItemRomaneioResponse(BaseModel):
    id: int
    produto: ProdutoRef
    unidade: str
    quantidade_sugerida: Decimal
    quantidade_final: Decimal = Field(description="O que vai para a loja (é a quantidade expedida, D76).")
    quantidade_recebida: Optional[Decimal]
    motivo_divergencia: Optional[str]
    observacao_divergencia: Optional[str]
    editado_em: Optional[datetime]
    motivo_edicao: Optional[str]


class EntregaRomaneioResponse(BaseModel):
    id: int
    loja: LojaRef
    situacao: SituacaoEntregaResponse
    expedido_em: Optional[datetime]
    recebido_em: Optional[datetime]
    itens: list[ItemRomaneioResponse]


class ProducaoRomaneioResponse(BaseModel):
    produto: ProdutoRef
    unidade: str
    tipo_abastecimento: str
    planejado: Decimal
    produzido: Optional[Decimal]
    total_final: Decimal = Field(description="Soma das finais das lojas; ao aprovar, não pode passar do produzido.")


class RomaneioDetalheResponse(BaseModel):
    id: int
    ordem_id: int
    data_producao: date
    data_entrega: date
    status: str
    gerado_em: datetime
    aprovado_em: Optional[datetime]
    desatualizado: bool = Field(description="Rascunho com a produção mudada depois de gerado: gere de novo (D87).")
    producao: list[ProducaoRomaneioResponse]
    entregas: list[EntregaRomaneioResponse]


class EditarItemRomaneioRequest(BaseModel):
    quantidade_final: Decimal = Field(description="Quanto mandar para a loja (UN inteiro; KG até 3 casas).")
    motivo: Optional[str] = Field(None, max_length=255, description="Motivo do ajuste (opcional).")


class RegistrarSaidaRequest(BaseModel):
    entrega_ids: Optional[list[int]] = Field(
        None, description="Entregas (lojas) que saíram; ausente = todas as que ainda aguardam saída.")


class SaidaResponse(BaseModel):
    entregas: list[int] = Field(description="Entregas com a saída registrada agora.")


class DivergenciaResponse(BaseModel):
    data_entrega: date
    loja: LojaRef
    produto: ProdutoRef
    unidade: str
    quantidade_enviada: Decimal
    quantidade_recebida: Decimal
    diferenca: Decimal = Field(description="Recebida − enviada (negativa = chegou menos).")
    motivo: str = Field(description="falta, avaria, a_mais ou outro (D78).")
    observacao: Optional[str]
    recebido_em: datetime


class TotalDivergenciaResponse(BaseModel):
    unidade: str
    enviada: Decimal
    recebida: Decimal
    diferenca: Decimal


class DivergenciasResponse(BaseModel):
    data_inicio: date
    data_fim: date
    divergencias: list[DivergenciaResponse]
    totais: list[TotalDivergenciaResponse]


# ---------------------------------------------------------------- recebimento no app (E7)

class ItemRecebimentoResponse(BaseModel):
    id: int
    produto: ProdutoRef
    unidade: str
    quantidade_expedida: Decimal
    quantidade_recebida: Optional[Decimal]
    motivo_divergencia: Optional[str]
    observacao_divergencia: Optional[str]


class EntregaRecebimentoResponse(BaseModel):
    id: int
    data_entrega: date
    expedido_em: Optional[datetime]
    recebido_em: Optional[datetime]
    situacao: SituacaoEntregaResponse
    itens: list[ItemRecebimentoResponse]


class DiferencaItemRequest(BaseModel):
    item_id: int
    quantidade_recebida: Decimal = Field(description="O que chegou bom na loja.")
    motivo: Optional[str] = Field(None, description="falta, avaria, a_mais ou outro (obrigatório se diferente).")
    observacao: Optional[str] = Field(None, max_length=255, description="Obrigatória com o motivo 'outro'.")


class ConfirmarRecebimentoRequest(BaseModel):
    diferencas: list[DiferencaItemRequest] = Field(
        default_factory=list,
        description="Só os itens que chegaram diferentes; vazio = 'Recebi tudo certo'.")
