"""
API da distribuição do SaaS web (Fase 5 / E6, D82). Routers finos:
autenticam o gestor (obter_gestor_central) e delegam aos serviços. Negócio
e central vêm sempre do gestor autenticado; não há `central_id` na URL
(regra de ouro 1).

- POST   /distribuicao/ordens/{ordem_id}/producao        produção real por item (D69)
- GET    /distribuicao/romaneios?data_entrega=AAAA-MM-DD ordens do dia de entrega, produção e romaneio (padrão: hoje)
- POST   /distribuicao/romaneios/gerar                   gera (ou gera de novo o rascunho) da ordem aprovada
- GET    /distribuicao/romaneios/{id}                    romaneio com as entregas por loja e a situação
- PATCH  /distribuicao/romaneios/{id}/itens/{item_id}    final de uma loja + produto (só rascunho)
- POST   /distribuicao/romaneios/{id}/aprovar            rascunho -> aprovado
- DELETE /distribuicao/romaneios/{id}                    apaga o rascunho
- POST   /distribuicao/romaneios/{id}/saida              saída de uma, várias ou todas as lojas que faltam (D76)
- GET    /distribuicao/romaneios/{id}/pdf?lojas=...      PDF do romaneio aprovado (E8)
- GET    /distribuicao/divergencias?data_inicio=&data_fim= recebimentos com diferença (D78)

Respostas de erro (como a D65): 404 para ordem, romaneio, item ou entrega
inexistente ou de outra central/negócio (mesma mensagem); 409 quando a
situação não permite (ordem em rascunho, romaneio aprovado, saída
repetida, rascunho na impressão); 422 para regra ferida (quantidade
inválida, produção não registrada, mais do que o produzido, loja fora da
central, período inválido).
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.schemas.distribuicao import (
    DistribuicaoDoDiaResponse,
    DivergenciaResponse,
    DivergenciasResponse,
    EditarItemRomaneioRequest,
    EntregaRomaneioResponse,
    GeracaoRomaneioResponse,
    GerarRomaneioRequest,
    ItemProducaoResponse,
    ItemRomaneioResponse,
    LojaRef,
    OrdemDistribuicaoResponse,
    ProducaoRomaneioResponse,
    ProdutoRef,
    RegistrarProducaoRequest,
    RegistrarProducaoResponse,
    RegistrarSaidaRequest,
    ResumoRomaneioResponse,
    RomaneioDetalheResponse,
    SaidaResponse,
    SituacaoEntregaResponse,
    TotalDivergenciaResponse,
)
from app.services.distribuicao_consulta_service import (
    RomaneioDetalhe,
    distribuicao_do_dia,
    listar_divergencias,
    obter_romaneio,
)
from app.services.distribuicao_service import (
    DistribuicaoInvalida,
    NaoEncontrado,
    OperacaoNaoPermitida,
    apagar_romaneio,
    aprovar_romaneio,
    editar_item,
    gerar_romaneio,
    registrar_producao,
    registrar_saida,
)

router = APIRouter()

# Período máximo da lista de divergências.
DIAS_MAXIMOS_DIVERGENCIAS = 92


class _Erros:
    """Converte os erros dos serviços em respostas HTTP (bloco `with`)."""

    def __enter__(self):
        return self

    def __exit__(self, tipo, erro, _tb):
        if erro is None:
            return False
        if isinstance(erro, NaoEncontrado):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
        if isinstance(erro, OperacaoNaoPermitida):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
        if isinstance(erro, DistribuicaoInvalida):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
        return False


def _detalhe(r: RomaneioDetalhe) -> RomaneioDetalheResponse:
    return RomaneioDetalheResponse(
        id=r.romaneio_id, ordem_id=r.ordem_id, data_producao=r.data_producao, data_entrega=r.data_entrega,
        status=r.status, gerado_em=r.gerado_em, aprovado_em=r.aprovado_em, desatualizado=r.desatualizado,
        producao=[
            ProducaoRomaneioResponse(
                produto=ProdutoRef(id=p.produto_id, codigo=p.produto_codigo, nome=p.produto_nome),
                unidade=p.unidade, tipo_abastecimento=p.tipo_abastecimento, planejado=p.planejado,
                produzido=p.produzido, total_final=p.total_final,
            )
            for p in r.producao
        ],
        entregas=[
            EntregaRomaneioResponse(
                id=e.entrega_id, loja=LojaRef(id=e.loja_id, codigo=e.loja_codigo, nome=e.loja_nome),
                situacao=SituacaoEntregaResponse(situacao=e.situacao.situacao, pode_confirmar=e.situacao.pode_confirmar,
                                                 com_diferenca=e.situacao.com_diferenca),
                expedido_em=e.expedido_em, recebido_em=e.recebido_em,
                itens=[
                    ItemRomaneioResponse(
                        id=i.item_id, produto=ProdutoRef(id=i.produto_id, codigo=i.produto_codigo,
                                                         nome=i.produto_nome),
                        unidade=i.unidade, quantidade_sugerida=i.quantidade_sugerida,
                        quantidade_final=i.quantidade_final, quantidade_recebida=i.quantidade_recebida,
                        motivo_divergencia=i.motivo_divergencia, observacao_divergencia=i.observacao_divergencia,
                        editado_em=i.editado_em, motivo_edicao=i.motivo_edicao,
                    )
                    for i in e.itens
                ],
            )
            for e in r.entregas
        ],
    )


@router.post("/distribuicao/ordens/{ordem_id}/producao", response_model=RegistrarProducaoResponse)
def registrar_producao_real(
    ordem_id: int,
    corpo: RegistrarProducaoRequest,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Registra a produção real (ou o disponível do distribuído) dos itens da ordem aprovada."""
    quantidades = {}
    for x in corpo.itens:
        if x.item_id in quantidades:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Cada produto pode aparecer uma vez só.")
        quantidades[x.item_id] = x.quantidade
    with _Erros():
        r = registrar_producao(db, gestor.negocio_id, gestor.central_producao_id, ordem_id, quantidades,
                               gestor.usuario_id)
    return RegistrarProducaoResponse(itens_registrados=r.itens_registrados,
                                     romaneio_desatualizado=r.romaneio_desatualizado)


@router.get("/distribuicao/romaneios", response_model=DistribuicaoDoDiaResponse)
def listar(
    data_entrega: Optional[date] = Query(None, description="Dia de entrega (AAAA-MM-DD); padrão: hoje."),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ordens da central com entrega no dia, a produção registrada e o romaneio de cada uma (se houver)."""
    dia = data_entrega or date.today()
    ordens = distribuicao_do_dia(db, gestor.negocio_id, gestor.central_producao_id, dia)
    return DistribuicaoDoDiaResponse(data_entrega=dia, ordens=[
        OrdemDistribuicaoResponse(
            ordem_id=o.ordem_id, data_producao=o.data_producao, data_entrega=o.data_entrega,
            status_ordem=o.status_ordem,
            itens=[
                ItemProducaoResponse(
                    item_id=i.item_id, produto=ProdutoRef(id=i.produto_id, codigo=i.produto_codigo,
                                                          nome=i.produto_nome),
                    unidade=i.unidade, tipo_abastecimento=i.tipo_abastecimento, planejado=i.planejado,
                    produzido=i.produzido, registrado_em=i.registrado_em,
                )
                for i in o.itens
            ],
            romaneio=ResumoRomaneioResponse(id=o.romaneio.romaneio_id, status=o.romaneio.status,
                                            entregas=o.romaneio.entregas, situacoes=o.romaneio.situacoes)
            if o.romaneio else None,
        )
        for o in ordens
    ])


@router.post("/distribuicao/romaneios/gerar", response_model=GeracaoRomaneioResponse)
def gerar(
    corpo: GerarRomaneioRequest,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Gera o romaneio da ordem aprovada (substitui o rascunho; aprovado -> 409; sem produção -> 422)."""
    with _Erros():
        r = gerar_romaneio(db, gestor.negocio_id, gestor.central_producao_id, corpo.ordem_id, gestor.usuario_id)
    return GeracaoRomaneioResponse(
        romaneio_id=r.romaneio_id, ordem_id=r.ordem_id, entregas=r.entregas, itens=r.itens,
        produtos_com_escassez=list(r.produtos_com_escassez), produtos_com_sobra=list(r.produtos_com_sobra),
        substituiu_rascunho=r.substituiu_rascunho,
    )


@router.get("/distribuicao/romaneios/{romaneio_id}", response_model=RomaneioDetalheResponse)
def detalhar(
    romaneio_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Romaneio com a produção por produto e as entregas por loja (na ordem do código), com a situação."""
    with _Erros():
        return _detalhe(obter_romaneio(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id))


@router.patch("/distribuicao/romaneios/{romaneio_id}/itens/{item_id}", response_model=RomaneioDetalheResponse)
def editar(
    romaneio_id: int,
    item_id: int,
    corpo: EditarItemRomaneioRequest,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Ajusta a final de uma loja + produto (só em rascunho; o item tem de ser deste romaneio)."""
    with _Erros():
        editar_item(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id, item_id, corpo.quantidade_final,
                    gestor.usuario_id, motivo=corpo.motivo)
        return _detalhe(obter_romaneio(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id))


@router.post("/distribuicao/romaneios/{romaneio_id}/aprovar", response_model=RomaneioDetalheResponse)
def aprovar(
    romaneio_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Aprova o rascunho (Σ final de cada produto <= produzido; lojas ativas na central)."""
    with _Erros():
        aprovar_romaneio(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id, gestor.usuario_id)
        return _detalhe(obter_romaneio(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id))


@router.delete("/distribuicao/romaneios/{romaneio_id}", status_code=status.HTTP_204_NO_CONTENT)
def apagar(
    romaneio_id: int,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Apaga um rascunho (aprovado -> 409)."""
    with _Erros():
        apagar_romaneio(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/distribuicao/romaneios/{romaneio_id}/saida", response_model=SaidaResponse)
def saida(
    romaneio_id: int,
    corpo: Optional[RegistrarSaidaRequest] = None,
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Registra a saída das lojas escolhidas (sem lista = todas as que faltam). Não se desfaz (D76)."""
    with _Erros():
        entregas = registrar_saida(db, gestor.negocio_id, gestor.central_producao_id, romaneio_id,
                                   gestor.usuario_id, corpo.entrega_ids if corpo else None)
    return SaidaResponse(entregas=sorted(e.id for e in entregas))


@router.get("/distribuicao/divergencias", response_model=DivergenciasResponse)
def divergencias(
    data_inicio: Optional[date] = Query(None, description="Primeiro dia de entrega (padrão: 6 dias antes do fim)."),
    data_fim: Optional[date] = Query(None, description="Último dia de entrega (padrão: hoje)."),
    db: Session = Depends(get_db),
    gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
):
    """Itens recebidos diferentes do enviado (D78), por dia, loja e produto, com os totais por unidade."""
    fim = data_fim or date.today()
    inicio = data_inicio or fim - timedelta(days=6)
    if inicio > fim:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="A data inicial não pode ser depois da final.")
    if (fim - inicio).days >= DIAS_MAXIMOS_DIVERGENCIAS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Escolha um período de até {DIAS_MAXIMOS_DIVERGENCIAS} dias.")
    linhas, totais = listar_divergencias(db, gestor.negocio_id, gestor.central_producao_id, inicio, fim)
    return DivergenciasResponse(
        data_inicio=inicio, data_fim=fim,
        divergencias=[
            DivergenciaResponse(
                data_entrega=d.data_entrega, loja=LojaRef(id=d.loja_id, codigo=d.loja_codigo, nome=d.loja_nome),
                produto=ProdutoRef(id=d.produto_id, codigo=d.produto_codigo, nome=d.produto_nome), unidade=d.unidade,
                quantidade_enviada=d.quantidade_enviada, quantidade_recebida=d.quantidade_recebida,
                diferenca=d.diferenca, motivo=d.motivo, observacao=d.observacao, recebido_em=d.recebido_em,
            )
            for d in linhas
        ],
        totais=[TotalDivergenciaResponse(unidade=t.unidade, enviada=t.enviada, recebida=t.recebida,
                                         diferenca=t.diferenca) for t in totais],
    )
