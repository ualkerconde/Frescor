"""
Schemas usados pelo endpoint manual de zeragem (uso administrativo/teste).
"""

from pydantic import BaseModel


class ResultadoZeragemLoja(BaseModel):
    loja_id: int
    loja_nome: str
    produtos_processados: int


class ExecutarZeragemResponse(BaseModel):
    lojas_processadas: int
    detalhes: list[ResultadoZeragemLoja]
