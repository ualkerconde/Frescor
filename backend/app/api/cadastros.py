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

Produto (C2; D96–D99, D101, D105) -- o catálogo é do negócio:
- GET /web/produtos/{id}: o cadastro completo, com calendário e setor.
- POST /web/produtos: cria (201); por padrão já ativo nas lojas ativas
  da central (D101).
- PATCH /web/produtos/{id}: só os campos enviados.
  (A lista continua em GET /web/produtos.)

Produto por loja (C3; D100) -- só as lojas da central do gestor:
- GET /web/produtos/{id}/lojas: cada loja e a situação do produto nela.
- PUT /web/produtos/{id}/lojas/{loja_id} {"ativo": true|false}.
Produto de outro negócio, loja de outra central ou inexistentes -> 404.

Erros de validação -> 422 com a mensagem em português em `detail`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.cadastro import (
    CentralEditar,
    CentralResponse,
    LojaDoProdutoEditar,
    LojaDoProdutoResponse,
    ProdutoCriar,
    ProdutoDetalheResponse,
    ProdutoEditar,
    SetorCriar,
    SetorDoProduto,
    SetorEditar,
)
from app.schemas.producao import SetorResponse
from app.services.cadastro_central_service import (
    CadastroInvalido,
    DadosCentral,
    criar_setor,
    editar_central,
    editar_setor,
    ler_central,
)
from app.services.cadastro_produto_service import (
    LojaDoProduto,
    ProdutoDetalhe,
    criar_produto,
    definir_loja,
    detalhar_produto,
    editar_produto,
    lojas_do_produto,
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


# ---------------------------------------------------------------- produto


def _produto(d: ProdutoDetalhe) -> ProdutoDetalheResponse:
    p = d.produto
    return ProdutoDetalheResponse(
        id=p.id, codigo=p.codigo, nome=p.nome, codigo_barras=p.codigo_barras, unidade=p.unidade_medida.value,
        peso_medio_kg=p.peso_medio_kg, ativo=p.ativo, tipo_abastecimento=p.tipo_abastecimento,
        dias_validade=p.dias_validade, margem_maxima_percentual=p.margem_maxima_percentual,
        data_inicio_vigencia=p.data_inicio_vigencia, data_fim_vigencia=p.data_fim_vigencia,
        vigencia_recorrente=p.vigencia_recorrente, ciclo_previsao=p.ciclo_previsao,
        setor=SetorDoProduto(id=p.setor_producao_id, nome=d.setor_nome) if d.setor_nome is not None else None,
        dias_producao=d.dias_producao, tem_historico=d.tem_historico,
    )


def _loja(x: LojaDoProduto) -> LojaDoProdutoResponse:
    return LojaDoProdutoResponse(
        loja_id=x.loja_id, codigo=x.codigo, nome=x.nome, loja_ativa=x.loja_ativa, habilitado=x.habilitado, ativo=x.ativo
    )


@router.get("/web/produtos/{produto_id}", response_model=ProdutoDetalheResponse)
def produto(
    produto_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Cadastro completo de um produto do negócio do gestor."""
    with _Erros():
        return _produto(detalhar_produto(db, gestor, produto_id))


@router.post("/web/produtos", response_model=ProdutoDetalheResponse, status_code=status.HTTP_201_CREATED)
def novo_produto(
    corpo: ProdutoCriar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Cria um produto no negócio do gestor (código obrigatório, D97)."""
    dados = corpo.model_dump(include=corpo.model_fields_set - {"habilitar_lojas"})
    dados.setdefault("nome", corpo.nome)
    dados.setdefault("codigo", corpo.codigo)
    with _Erros():
        return _produto(criar_produto(db, gestor, dados, habilitar_lojas=corpo.habilitar_lojas))


@router.patch("/web/produtos/{produto_id}", response_model=ProdutoDetalheResponse)
def alterar_produto(
    produto_id: int,
    corpo: ProdutoEditar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Muda os campos enviados do produto. Vale para a próxima previsão e a próxima ordem."""
    with _Erros():
        return _produto(editar_produto(db, gestor, produto_id, corpo.model_dump(include=corpo.model_fields_set)))


@router.get("/web/produtos/{produto_id}/lojas", response_model=list[LojaDoProdutoResponse])
def lojas_produto(
    produto_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Lojas da central do gestor e a situação do produto em cada uma (D100)."""
    with _Erros():
        return [_loja(x) for x in lojas_do_produto(db, gestor, produto_id)]


@router.put("/web/produtos/{produto_id}/lojas/{loja_id}", response_model=LojaDoProdutoResponse)
def definir_loja_produto(
    produto_id: int,
    loja_id: int,
    corpo: LojaDoProdutoEditar,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ativa (habilita, se preciso) ou desativa o produto numa loja da central (D100)."""
    with _Erros():
        return _loja(definir_loja(db, gestor, produto_id, loja_id, corpo.ativo))
