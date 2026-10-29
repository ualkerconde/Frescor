"""
Cadastros do SaaS web (Fase 6). Routers finos: autenticam com
obter_gestor_central e delegam aos serviços de cadastro, que aplicam o
escopo (negócio e central vêm do gestor, nunca da requisição).

Central e setores (C1; D102, D103):
- GET /web/central: a central do gestor.
- PATCH /web/central: nome e/ou prazo de entrega.
- POST /producao/setores: cria (201) um setor na central do gestor.
- PATCH /producao/setores/{id}: nome, ordem e/ou ativo. Setor de outra
  central, de outro negócio ou inexistente -> 404, sem distinguir.
  (A lista continua em GET /producao/setores.)

Erros de validação -> 422 com a mensagem em português em `detail`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.cadastro import CentralEditar, CentralResponse, SetorCriar, SetorEditar
from app.schemas.producao import SetorResponse
from app.services.cadastro_central_service import (
    CadastroInvalido,
    DadosCentral,
    criar_setor,
    editar_central,
    editar_setor,
    ler_central,
)

router = APIRouter()


class _Erros:
    """Converte os erros dos serviços em respostas HTTP (bloco `with`)."""

    def __enter__(self):
        return self

    def __exit__(self, tipo, erro, _tb):
        if erro is None:
            return False
        if isinstance(erro, LookupError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
        if isinstance(erro, CadastroInvalido):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
        return False


def _central(d: DadosCentral) -> CentralResponse:
    return CentralResponse(
        id=d.id, nome=d.nome, secao=d.secao, prazo_entrega_dias=d.prazo_entrega_dias, ativa=d.ativa, lojas=d.lojas
    )


def _setor(s) -> SetorResponse:
    return SetorResponse(id=s.id, nome=s.nome, ordem=s.ordem, ativo=s.ativo)


@router.get("/web/central", response_model=CentralResponse)
def central(db: Session = Depends(get_db), gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    """A central do gestor: nome, seção, prazo de entrega, situação e número de lojas."""
    return _central(ler_central(db, gestor))


@router.patch("/web/central", response_model=CentralResponse)
def alterar_central(
    corpo: CentralEditar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Muda o nome e/ou o prazo de entrega da central (D103). Só os campos enviados."""
    with _Erros():
        return _central(editar_central(db, gestor, **corpo.model_dump(include=corpo.model_fields_set)))


@router.post("/producao/setores", response_model=SetorResponse, status_code=status.HTTP_201_CREATED)
def novo_setor(
    corpo: SetorCriar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Cria um setor de produção na central do gestor (D102)."""
    with _Erros():
        return _setor(criar_setor(db, gestor, corpo.nome, corpo.ordem))


@router.patch("/producao/setores/{setor_id}", response_model=SetorResponse)
def alterar_setor(
    setor_id: int,
    corpo: SetorEditar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Renomeia, muda a ordem e/ou ativa/desativa um setor (sem apagar, D102). Só os campos enviados."""
    with _Erros():
        return _setor(editar_setor(db, gestor, setor_id, **corpo.model_dump(include=corpo.model_fields_set)))
