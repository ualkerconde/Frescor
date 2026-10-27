"""
API da ordem de produção do SaaS web (Fase 4 / N7). Routers finos:
autenticam o gestor (obter_gestor_central) e delegam aos serviços. Negócio
e central vêm sempre do gestor autenticado; não há `central_id` na URL
(regra de ouro 1; divergência aprovada com o doc §8).

- POST   /producao/ordens/gerar                  gera (ou regera o rascunho) da data
- GET    /producao/ordens?data=AAAA-MM-DD        ordens do dia, em resumo (padrão: amanhã)
- GET    /producao/ordens/{id}                   ordem com itens e linhas por loja
- PATCH  /producao/ordens/{id}/linhas/{linha_id} quantidade final de uma loja (só rascunho)
- POST   /producao/ordens/{id}/aprovar           rascunho -> aprovada
- DELETE /producao/ordens/{id}                   apaga um rascunho
- GET    /producao/ordens/{id}/pdf?setores=...   PDF da ordem APROVADA, uma folha por setor (D67)
- GET    /producao/setores                       setores de produção da central (D67)

Respostas de erro: 404 para ordem/linha inexistente ou de outra central ou
negócio (mesma mensagem, sem revelar se existe); 409 para ordem aprovada
(não é editada, regerada nem apagada) e para imprimir ordem que ainda não
foi aprovada; 422 para pedido que fere uma regra
(data fora do permitido, quantidade inválida, linha sem quantidade ao
aprovar, loja fora da central).
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.producao import (
    EditarLinhaRequest,
    GeracaoOrdemResponse,
    GerarOrdemRequest,
    ItemOrdemResponse,
    LinhaOrdemResponse,
    LojaOrdem,
    OrdemDetalheResponse,
    OrdemResumoResponse,
    OrdensDoDiaResponse,
    ProdutoOrdem,
    SetorResponse,
    TotalUnidadeResponse,
)
from app.services.necessidade_service import CentralNaoEncontrada
from app.services.ordem_pdf_service import (
    SEM_SETOR,
    OrdemNaoAprovada,
    gerar_pdf,
    montar_impressao,
    setores_da_central,
)
from app.services.producao_consulta_service import LinhaOrdem, ResumoOrdem, listar_ordens, obter_ordem
from app.services.producao_service import (
    OrdemAprovada,
    OrdemInvalida,
    OrdemNaoEncontrada,
    apagar_ordem,
    aprovar_ordem,
    editar_linha,
    gerar_ordem,
)

router = APIRouter()


class _Erros:
    """Converte os erros dos serviços em respostas HTTP (bloco `with`)."""

    def __enter__(self):
        return self

    def __exit__(self, tipo, erro, _tb):
        if erro is None:
            return False
        if isinstance(erro, (OrdemNaoEncontrada, CentralNaoEncontrada)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
        if isinstance(erro, (OrdemAprovada, OrdemNaoAprovada)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
        if isinstance(erro, OrdemInvalida):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
        return False


def _linha(x: LinhaOrdem) -> LinhaOrdemResponse:
    return LinhaOrdemResponse(
        id=x.id, loja=LojaOrdem(id=x.loja_id, codigo=x.loja_codigo, nome=x.loja_nome),
        quantidade_sugerida=x.quantidade_sugerida, quantidade_final=x.quantidade_final, editada=x.editada,
        editado_em=x.editado_em, motivo_edicao=x.motivo_edicao, avisos=x.avisos, componentes=x.componentes,
    )


def _resumo(r: ResumoOrdem) -> dict:
    return dict(
        id=r.id, data_producao=r.data_producao, data_entrega=r.data_entrega, tipo=r.tipo, status=r.status,
        versao_metodo=r.versao_metodo, referencia_previsao=r.referencia_previsao, gerado_em=r.gerado_em,
        gerado_por=r.gerado_por, aprovado_em=r.aprovado_em, aprovado_por=r.aprovado_por, linhas=r.linhas,
        linhas_editadas=r.linhas_editadas, linhas_sem_quantidade=r.linhas_sem_quantidade,
        totais=[TotalUnidadeResponse(unidade=t.unidade, sugerido=t.sugerido, final=t.final) for t in r.totais],
    )


def _detalhe(r: ResumoOrdem) -> OrdemDetalheResponse:
    return OrdemDetalheResponse(
        **_resumo(r),
        itens=[
            ItemOrdemResponse(
                id=i.id, produto=ProdutoOrdem(id=i.produto_id, codigo=i.produto_codigo, nome=i.produto_nome),
                tipo_abastecimento=i.tipo_abastecimento, unidade=i.unidade, total_sugerido=i.total_sugerido,
                total_final=i.total_final, linhas=[_linha(x) for x in i.linhas],
            )
            for i in r.itens
        ],
    )


@router.post("/producao/ordens/gerar", response_model=GeracaoOrdemResponse)
def gerar(
    corpo: Optional[GerarOrdemRequest] = None,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Gera a ordem do dia da central do gestor (substitui o rascunho; ordem aprovada -> 409)."""
    hoje = date.today()
    dia = (corpo.data_producao if corpo else None) or hoje + timedelta(days=1)
    with _Erros():
        r = gerar_ordem(db, gestor.negocio_id, gestor.central_producao_id, dia, gestor.usuario_id, hoje)
    return GeracaoOrdemResponse(
        ordem_id=r.ordem_id, data_producao=r.data_producao, data_entrega=r.data_entrega, itens=r.itens,
        linhas=r.linhas, sem_quantidade=r.sem_quantidade, substituiu_rascunho=r.substituiu_rascunho,
        previsao_atualizada=r.previsao_atualizada,
    )


@router.get("/producao/ordens", response_model=OrdensDoDiaResponse)
def listar(
    data: Optional[date] = Query(None, description="Dia de produção (AAAA-MM-DD); padrão: amanhã."),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ordens da central do gestor num dia de produção (lista vazia = ainda não gerada)."""
    dia = data or date.today() + timedelta(days=1)
    ordens = listar_ordens(db, gestor.negocio_id, gestor.central_producao_id, dia)
    return OrdensDoDiaResponse(data_producao=dia, ordens=[OrdemResumoResponse(**_resumo(o)) for o in ordens])


@router.get("/producao/ordens/{ordem_id}", response_model=OrdemDetalheResponse)
def detalhar(
    ordem_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ordem com os itens por produto e as linhas por loja."""
    with _Erros():
        return _detalhe(obter_ordem(db, gestor.negocio_id, gestor.central_producao_id, ordem_id))


@router.patch("/producao/ordens/{ordem_id}/linhas/{linha_id}", response_model=LinhaOrdemResponse)
def editar(
    ordem_id: int,
    linha_id: int,
    corpo: EditarLinhaRequest,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ajusta a quantidade final de uma loja (só em rascunho; aprovada -> 409)."""
    with _Erros():
        editar_linha(db, gestor.negocio_id, gestor.central_producao_id, linha_id, corpo.quantidade_final,
                     gestor.usuario_id, motivo=corpo.motivo, ordem_id=ordem_id)
        ordem = obter_ordem(db, gestor.negocio_id, gestor.central_producao_id, ordem_id)
    linha = next(x for i in ordem.itens for x in i.linhas if x.id == linha_id)
    return _linha(linha)


@router.post("/producao/ordens/{ordem_id}/aprovar", response_model=OrdemResumoResponse)
def aprovar(
    ordem_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Aprova o rascunho (exige quantidade em todas as linhas; loja fora da central -> 422)."""
    with _Erros():
        aprovar_ordem(db, gestor.negocio_id, gestor.central_producao_id, ordem_id, gestor.usuario_id)
        return OrdemResumoResponse(**_resumo(obter_ordem(db, gestor.negocio_id, gestor.central_producao_id,
                                                         ordem_id)))


@router.delete("/producao/ordens/{ordem_id}", status_code=status.HTTP_204_NO_CONTENT)
def apagar(
    ordem_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Apaga um rascunho (ordem aprovada -> 409: é trânsito das próximas ordens)."""
    with _Erros():
        apagar_ordem(db, gestor.negocio_id, gestor.central_producao_id, ordem_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _ler_setores(texto: Optional[str]) -> list[int | str] | None:
    """'3,5,sem' -> [3, 5, 'sem']; vazio/ausente -> None (todos). Item inválido -> 422."""
    if texto is None or texto.strip() == "":
        return None
    escolhidos: list[int | str] = []
    for parte in texto.split(","):
        parte = parte.strip().lower()
        if parte == SEM_SETOR:
            escolhidos.append(SEM_SETOR)
        elif parte.isdigit():
            escolhidos.append(int(parte))
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Setores inválidos. Escolha os setores da lista.")
    return escolhidos


@router.get(
    "/producao/ordens/{ordem_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF da ordem, uma folha por setor."}},
)
def imprimir(
    ordem_id: int,
    setores: Optional[str] = Query(
        None, description="Ids dos setores separados por vírgula e/ou 'sem' (produtos sem setor); vazio = todos."
    ),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """PDF da ordem APROVADA (rascunho -> 409), uma folha por setor; os setores escolhidos ou todos."""
    escolhidos = _ler_setores(setores)
    with _Erros():
        impressao = montar_impressao(db, gestor.negocio_id, gestor.central_producao_id, ordem_id, escolhidos)
    nome = f"ordem-producao-{impressao.data_producao:%Y-%m-%d}.pdf"
    return Response(
        content=gerar_pdf(impressao),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.get("/producao/setores", response_model=list[SetorResponse])
def listar_setores(
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Setores de produção da central do gestor (ativos e inativos), na ordem de exibição."""
    return [
        SetorResponse(id=s.id, nome=s.nome, ordem=s.ordem, ativo=s.ativo)
        for s in setores_da_central(db, gestor.negocio_id, gestor.central_producao_id)
    ]
