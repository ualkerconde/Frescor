"""
API do recebimento no app mobile (Fase 5 / E7, D77, D82). Routers finos:
autenticam o operador (obter_usuario_autenticado) e delegam ao
`recebimento_service`. A loja vem sempre do usuário autenticado (registro
atual no banco); não há loja na URL nem no corpo (regra de ouro 1).

- GET  /recebimentos                          entregas com saída registrada, a confirmar (dentro do prazo, D85)
- GET  /recebimentos/{entrega_id}             uma entrega da loja, com os itens
- POST /recebimentos/{entrega_id}/confirmar   "Recebi tudo certo" (sem diferenças) ou "com diferença"

Rotas novas: não mudam `/produtos`, `/estoque`, `/zeragem` nem `/auth`.

Erros: 404 para entrega inexistente ou de outra loja (mesma mensagem); 409
para entrega sem saída, já confirmada ou com o prazo encerrado; 422 para
quantidade ou motivo inválido.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import UsuarioAutenticado, obter_usuario_autenticado
from app.db.session import get_db
from app.schemas.distribuicao import (
    ConfirmarRecebimentoRequest,
    EntregaRecebimentoResponse,
    ItemRecebimentoResponse,
    ProdutoRef,
    SituacaoEntregaResponse,
)
from app.services.recebimento_service import (
    DiferencaItem,
    EntregaLoja,
    EntregaNaoEncontrada,
    RecebimentoInvalido,
    RecebimentoNaoPermitido,
    confirmar,
    detalhar,
    listar_pendentes,
)

router = APIRouter()


class _Erros:
    def __enter__(self):
        return self

    def __exit__(self, tipo, erro, _tb):
        if erro is None:
            return False
        if isinstance(erro, EntregaNaoEncontrada):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
        if isinstance(erro, RecebimentoNaoPermitido):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
        if isinstance(erro, RecebimentoInvalido):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
        return False


def _entrega(e: EntregaLoja) -> EntregaRecebimentoResponse:
    return EntregaRecebimentoResponse(
        id=e.entrega_id, data_entrega=e.data_entrega, expedido_em=e.expedido_em, recebido_em=e.recebido_em,
        situacao=SituacaoEntregaResponse(situacao=e.situacao.situacao, pode_confirmar=e.situacao.pode_confirmar,
                                         com_diferenca=e.situacao.com_diferenca),
        itens=[
            ItemRecebimentoResponse(
                id=i.item_id, produto=ProdutoRef(id=i.produto_id, codigo=i.produto_codigo, nome=i.produto_nome),
                unidade=i.unidade, quantidade_expedida=i.quantidade_expedida,
                quantidade_recebida=i.quantidade_recebida, motivo_divergencia=i.motivo_divergencia,
                observacao_divergencia=i.observacao_divergencia,
            )
            for i in e.itens
        ],
    )


def _loja(atual: UsuarioAutenticado) -> int:
    if atual.loja_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seu usuário não está ligado a uma loja.")
    return atual.loja_id


@router.get("/recebimentos", response_model=list[EntregaRecebimentoResponse])
def listar(
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """Entregas da loja com saída registrada, ainda não confirmadas e dentro do prazo, da mais antiga."""
    return [_entrega(e) for e in listar_pendentes(db, atual.negocio_id, _loja(atual))]


@router.get("/recebimentos/{entrega_id}", response_model=EntregaRecebimentoResponse)
def ver(
    entrega_id: int,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """Uma entrega da loja (com saída registrada), com os itens."""
    with _Erros():
        return _entrega(detalhar(db, atual.negocio_id, _loja(atual), entrega_id))


@router.post("/recebimentos/{entrega_id}/confirmar", response_model=EntregaRecebimentoResponse)
def confirmar_recebimento(
    entrega_id: int,
    corpo: ConfirmarRecebimentoRequest | None = None,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """Confirma o recebimento: sem diferenças = tudo certo; com diferenças, só os itens que vieram diferentes."""
    diferencas = {}
    for d in (corpo.diferencas if corpo else []):
        if d.item_id in diferencas:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Cada produto pode aparecer uma vez só.")
        diferencas[d.item_id] = DiferencaItem(d.quantidade_recebida, d.motivo, d.observacao)
    with _Erros():
        return _entrega(confirmar(db, atual.negocio_id, _loja(atual), entrega_id, atual.usuario_id,
                                  diferencas or None))
