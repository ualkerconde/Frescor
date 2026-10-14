"""
Endpoints de importação de vendas e perdas por CSV (SaaS web, Fase 2 / P5).

Routers finos: autenticam o gestor (obter_gestor_central), recebem o arquivo
por upload multipart, aplicam o limite de tamanho e delegam tudo ao
importacao_service, que tem as regras (D5, D6, D7, D8, D9, D12, D13 em
docs/STATUS.md).

Respostas:
- 200: importado; corpo com o relatório (inseridas, substituídas, avisos).
- 422: arquivo com erros, nada gravado; corpo com o MESMO relatório, com os
  erros por linha. (Um 422 sem o campo `sucesso` é a validação do próprio
  FastAPI, ex.: campo `arquivo` ausente no formulário.)
- 413: arquivo maior que o limite, nada processado.
- 401/403: as da obter_gestor_central.

Limite de tamanho: o Starlette recebe e guarda o upload inteiro antes de a
rota rodar, então o limite daqui impede o PROCESSAMENTO de um arquivo
grande, não o recebimento. A proteção contra uploads enormes é um limite de
corpo no servidor da frente (ex.: client_max_body_size no nginx).
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.importacao import RelatorioImportacaoResponse
from app.services.importacao_service import TipoImportacao, importar_csv

LIMITE_ARQUIVO_BYTES = 5 * 1024 * 1024  # 5 MB: folga para as 100.000 linhas do serviço

router = APIRouter()

_RESPOSTAS = {
    422: {"model": RelatorioImportacaoResponse, "description": "Arquivo com erros; nada foi gravado."},
    413: {"description": f"Arquivo maior que {LIMITE_ARQUIVO_BYTES // (1024 * 1024)} MB."},
}


def _ler_com_limite(arquivo: UploadFile) -> bytes:
    conteudo = arquivo.file.read(LIMITE_ARQUIVO_BYTES + 1)
    if len(conteudo) > LIMITE_ARQUIVO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo maior que {LIMITE_ARQUIVO_BYTES // (1024 * 1024)} MB. Divida em arquivos menores.",
        )
    return conteudo


def _importar(db: Session, gestor: GestorCentralAutenticado, arquivo: UploadFile, tipo: TipoImportacao):
    resultado = importar_csv(db, gestor, _ler_com_limite(arquivo), tipo)
    corpo = RelatorioImportacaoResponse(**asdict(resultado))
    if not resultado.sucesso:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=corpo.model_dump())
    return corpo


@router.post("/vendas/importar", response_model=RelatorioImportacaoResponse, responses=_RESPOSTAS)
def importar_vendas(
    arquivo: UploadFile = File(..., description="CSV: data;codigo_loja;codigo_produto;quantidade"),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Importa vendas diárias de um CSV (tudo ou nada; reimportação substitui)."""
    return _importar(db, gestor, arquivo, TipoImportacao.VENDA)


@router.post("/perdas/importar", response_model=RelatorioImportacaoResponse, responses=_RESPOSTAS)
def importar_perdas(
    arquivo: UploadFile = File(..., description="CSV: data;codigo_loja;codigo_produto;quantidade"),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Importa perdas diárias de um CSV (tudo ou nada; reimportação substitui)."""
    return _importar(db, gestor, arquivo, TipoImportacao.PERDA)
