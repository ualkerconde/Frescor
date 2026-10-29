"""
Rotas de apoio às telas do SaaS web (frontend, passo W1), com prefixo
/web (decisão DF4: /produtos já é rota do app mobile).

- GET /web/me: quem está logado (gestor, central, negócio), para o cabeçalho.
- GET /web/lojas: lojas da central do gestor (D8), para o filtro de loja.
- GET /web/produtos: produtos do negócio, com busca, para o filtro de produto
  e a lista do cadastro (Fase 6: tipo, setor e lojas ativas da central).

Todas exigem o token do SaaS (obter_gestor_central): 401 sem token ou com
token do app; 403 sem permissão.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.models.loja import Loja
from app.models.setor_producao import SetorProducao
from app.schemas.web import (
    CentralResumo,
    LojaWebResponse,
    MeResponse,
    NegocioResumo,
    ProdutosWebResponse,
    ProdutoWebResponse,
    UsuarioResumo,
)
from app.services.cadastro_produto_service import contar_lojas_ativas
from app.services.catalogo_service import dados_do_gestor, listar_produtos
from app.services.escopo_service import consulta_lojas_do_gestor

LIMIT_MAXIMO_PRODUTOS = 200

router = APIRouter()


@router.get("/me", response_model=MeResponse)
def me(db: Session = Depends(get_db), gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    """Gestor logado, sua central e seu negócio."""
    d = dados_do_gestor(db, gestor)
    return MeResponse(
        usuario=UsuarioResumo(id=d.usuario_id, nome=d.nome, email=d.email),
        central=CentralResumo(id=d.central_id, nome=d.central_nome),
        negocio=NegocioResumo(id=d.negocio_id, nome=d.negocio_nome),
    )


@router.get("/lojas", response_model=list[LojaWebResponse])
def lojas(db: Session = Depends(get_db), gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    """Lojas da central do gestor (ativas e inativas), por código e nome."""
    lojas_escopo = consulta_lojas_do_gestor(db, gestor).order_by(Loja.codigo.asc().nulls_last(), Loja.nome, Loja.id)
    return [LojaWebResponse(id=lj.id, codigo=lj.codigo, nome=lj.nome, ativo=lj.ativo) for lj in lojas_escopo]


@router.get("/produtos", response_model=ProdutosWebResponse)
def produtos(
    busca: Optional[str] = Query(None, description="Trecho do código ou do nome (sem diferenciar maiúsculas)."),
    limit: int = Query(50, ge=1, le=LIMIT_MAXIMO_PRODUTOS),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Produtos do negócio do gestor (ativos e inativos), com busca e paginação."""
    total, itens = listar_produtos(db, gestor, busca, limit, offset)
    ids_setores = {p.setor_producao_id for p in itens if p.setor_producao_id is not None}
    setores = dict(
        db.query(SetorProducao.id, SetorProducao.nome).filter(
            SetorProducao.negocio_id == gestor.negocio_id, SetorProducao.id.in_(ids_setores)
        )
    ) if ids_setores else {}
    lojas_ativas = contar_lojas_ativas(db, gestor, [p.id for p in itens])
    return ProdutosWebResponse(
        total=total,
        limit=limit,
        offset=offset,
        itens=[
            ProdutoWebResponse(
                id=p.id, codigo=p.codigo, nome=p.nome, unidade=p.unidade_medida.value, ativo=p.ativo,
                tipo_abastecimento=p.tipo_abastecimento.value, setor=setores.get(p.setor_producao_id),
                lojas_ativas=lojas_ativas.get(p.id, 0),
            )
            for p in itens
        ],
    )
