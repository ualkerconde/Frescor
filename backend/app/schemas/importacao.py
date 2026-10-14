"""
Schemas da importação de vendas e perdas por CSV (SaaS web, Fase 2 / P5).

O mesmo formato de relatório é devolvido com 200 (importado) e com 422
(arquivo com erros, nada gravado), para o frontend mostrar o resultado de
um jeito só.
"""

from pydantic import BaseModel, Field


class MensagemLinha(BaseModel):
    linha: int = Field(description="Linha do arquivo (o cabeçalho é a linha 1; 0 = o arquivo como um todo).")
    mensagem: str


class RelatorioImportacaoResponse(BaseModel):
    sucesso: bool = Field(description="true: tudo gravado. false: nada gravado (tudo ou nada).")
    linhas_lidas: int
    inseridas: int
    substituidas: int = Field(description="Linhas que já existiam (mesma loja, produto, data e origem) e foram substituídas.")
    codificacao: str = Field(description="Codificação detectada do arquivo: utf-8 ou windows-1252.")
    erros: list[MensagemLinha]
    erros_omitidos: int = Field(description="Erros além dos listados (a lista é limitada).")
    avisos: list[MensagemLinha] = Field(description="Pontos de atenção que não impedem a importação.")
    avisos_omitidos: int
