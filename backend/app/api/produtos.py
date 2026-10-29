"""
Endpoints de produtos e estoque, consumidos pelo app móvel (PWA).

Busca unificada: GET /produtos/buscar aceita o parâmetro `q` que procura
simultaneamente em `codigo` (código interno) e `codigo_barras` (scanner).
O app sempre usa este endpoint, independente do tipo de código cadastrado.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import UsuarioAutenticado, obter_usuario_autenticado
from app.db.session import get_db
from app.models.estoque_atual import EstoqueAtual
from app.models.produto import Produto
from app.models.produto_loja import ProdutoLoja
from app.schemas.estoque import (
    AtualizarEstoqueRequest,
    EstoqueResponse,
    ProdutoComEstoqueResponse,
    SincronizarEstoqueRequest,
    SincronizarEstoqueResponse,
)
from app.services.classificacao_service import obter_classificacoes_por_produto
from app.services.estoque_service import aplicar_contagem, sincronizar_contagens

router = APIRouter()


def _requer_peso_informado(produto: Produto) -> bool:
    """
    True quando o produto é KG e não tem peso médio cadastrado — cenário em
    que o responsável pela contagem pesa o item na hora (ex.: bolo vendido
    por fatia) em vez de contar peças com um peso médio fixo.
    """
    return produto.unidade_medida.value == "KG" and produto.peso_medio_kg is None


@router.get("/produtos", response_model=list[ProdutoComEstoqueResponse])
def listar_produtos(
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """
    Lista os produtos habilitados para a loja do usuário autenticado,
    já com os dois valores de estoque daquela loja.
    """
    resultados = (
        db.query(
            Produto,
            EstoqueAtual.quantidade_inventariada,
            EstoqueAtual.estoque_atual_calculado,
            EstoqueAtual.peso_informado_kg,
        )
        .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
        .outerjoin(
            EstoqueAtual,
            (EstoqueAtual.produto_id == Produto.id) & (EstoqueAtual.loja_id == atual.loja_id),
        )
        .filter(
            ProdutoLoja.loja_id == atual.loja_id,
            # Desativado na loja pelo SaaS (D100, Fase 6): sai da contagem.
            ProdutoLoja.ativo.is_(True),
            Produto.negocio_id == atual.negocio_id,
            Produto.ativo.is_(True),
        )
        .order_by(Produto.nome)
        .all()
    )

    classificacoes = obter_classificacoes_por_produto(
        db=db,
        produto_ids=[produto.id for produto, *_ in resultados],
        negocio_id=atual.negocio_id,
    )

    return [
        ProdutoComEstoqueResponse(
            id=produto.id,
            nome=produto.nome,
            codigo=produto.codigo,
            codigo_barras=produto.codigo_barras,
            unidade_medida=produto.unidade_medida.value,
            quantidade_inventariada=quantidade_inventariada if quantidade_inventariada is not None else 0,
            estoque_atual_calculado=estoque_calculado if estoque_calculado is not None else Decimal("0"),
            peso_informado_kg=peso_informado_kg,
            requer_peso_informado=_requer_peso_informado(produto),
            classificacao=classificacoes.get(produto.id, []),
        )
        for produto, quantidade_inventariada, estoque_calculado, peso_informado_kg in resultados
    ]


@router.get("/produtos/buscar", response_model=ProdutoComEstoqueResponse)
def buscar_produto(
    q: str,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """
    Busca unificada: localiza um produto pelo parâmetro `q`, procurando
    simultaneamente em `codigo` (código interno) e `codigo_barras` (scanner).

    O app sempre envia o valor lido/digitado como `q`, sem precisar saber
    qual tipo de código o produto usa.
    """
    resultado = (
        db.query(
            Produto,
            EstoqueAtual.quantidade_inventariada,
            EstoqueAtual.estoque_atual_calculado,
            EstoqueAtual.peso_informado_kg,
        )
        .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
        .outerjoin(
            EstoqueAtual,
            (EstoqueAtual.produto_id == Produto.id) & (EstoqueAtual.loja_id == atual.loja_id),
        )
        .filter(
            ProdutoLoja.loja_id == atual.loja_id,
            ProdutoLoja.ativo.is_(True),  # D100
            Produto.negocio_id == atual.negocio_id,
            Produto.ativo.is_(True),
            or_(
                Produto.codigo == q,
                Produto.codigo_barras == q,
            ),
        )
        .first()
    )

    if resultado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum produto encontrado com este código para esta loja.",
        )

    produto, quantidade_inventariada, estoque_calculado, peso_informado_kg = resultado
    classificacoes = obter_classificacoes_por_produto(
        db=db,
        produto_ids=[produto.id],
        negocio_id=atual.negocio_id,
    )
    return ProdutoComEstoqueResponse(
        id=produto.id,
        nome=produto.nome,
        codigo=produto.codigo,
        codigo_barras=produto.codigo_barras,
        unidade_medida=produto.unidade_medida.value,
        quantidade_inventariada=quantidade_inventariada if quantidade_inventariada is not None else 0,
        estoque_atual_calculado=estoque_calculado if estoque_calculado is not None else Decimal("0"),
        peso_informado_kg=peso_informado_kg,
        requer_peso_informado=_requer_peso_informado(produto),
        classificacao=classificacoes.get(produto.id, []),
    )


@router.patch("/estoque/{produto_id}", response_model=EstoqueResponse)
def atualizar_estoque(
    produto_id: int,
    dados: AtualizarEstoqueRequest,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    try:
        estoque = aplicar_contagem(
            db=db,
            negocio_id=atual.negocio_id,
            loja_id=atual.loja_id,
            produto_id=produto_id,
            quantidade_inventariada=dados.quantidade_inventariada,
            peso_informado_kg=dados.peso_informado_kg,
        )
    except ValueError as erro:
        if "não encontrado" in str(erro) or "não habilitado" in str(erro):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado ou não habilitado para esta loja.",
            )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro))
    return estoque


@router.post("/estoque/sincronizar", response_model=SincronizarEstoqueResponse)
def sincronizar_estoque(
    dados: SincronizarEstoqueRequest,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    produto_ids = sincronizar_contagens(
        db=db,
        negocio_id=atual.negocio_id,
        loja_id=atual.loja_id,
        contagens=dados.contagens,
    )
    return SincronizarEstoqueResponse(
        sincronizados=len(produto_ids),
        produto_ids=produto_ids,
    )
